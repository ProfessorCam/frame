/* frame recorder controls — GNOME Shell extension (GNOME 45+ / ESM).
 *
 * Shows a top-bar indicator with Pause/Resume + Stop while frame is recording.
 * It watches the frame app on the session bus and drives the
 * com.github.frame.Control D-Bus interface. The indicator is added only while
 * recording and removed when recording stops or the app quits.
 */

import GObject from 'gi://GObject';
import Gio from 'gi://Gio';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'com.github.frame';
const OBJECT_PATH = '/com/github/frame/Control';

const FrameIface = `<node>
  <interface name="com.github.frame.Control">
    <method name="Pause"/>
    <method name="Resume"/>
    <method name="TogglePause"/>
    <method name="Stop"/>
    <method name="GetState">
      <arg type="b" name="recording" direction="out"/>
      <arg type="b" name="paused" direction="out"/>
    </method>
    <signal name="StateChanged">
      <arg type="b" name="recording"/>
      <arg type="b" name="paused"/>
    </signal>
    <property name="Recording" type="b" access="read"/>
    <property name="Paused" type="b" access="read"/>
  </interface>
</node>`;

const FrameProxy = Gio.DBusProxy.makeProxyWrapper(FrameIface);

const FrameIndicator = GObject.registerClass(
class FrameIndicator extends PanelMenu.Button {
    _init(controller) {
        super._init(0.0, 'frame');
        this._controller = controller;

        this._icon = new St.Icon({
            icon_name: 'media-record-symbolic',
            style_class: 'system-status-icon frame-rec-icon',
        });
        this.add_child(this._icon);

        this._pauseItem = new PopupMenu.PopupMenuItem('Pause');
        this._pauseItem.connect('activate', () => this._controller.togglePause());
        this.menu.addMenuItem(this._pauseItem);

        this._stopItem = new PopupMenu.PopupMenuItem('Stop recording');
        this._stopItem.connect('activate', () => this._controller.stop());
        this.menu.addMenuItem(this._stopItem);
    }

    setPaused(paused) {
        this._pauseItem.label.text = paused ? 'Resume' : 'Pause';
        if (paused)
            this._icon.add_style_class_name('frame-paused');
        else
            this._icon.remove_style_class_name('frame-paused');
    }
});

export default class FrameExtension extends Extension {
    enable() {
        this._proxy = null;
        this._indicator = null;
        this._signalId = 0;
        this._watchId = Gio.bus_watch_name(
            Gio.BusType.SESSION, BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            this._onNameAppeared.bind(this),
            this._onNameVanished.bind(this));
    }

    disable() {
        if (this._watchId) {
            Gio.bus_unwatch_name(this._watchId);
            this._watchId = 0;
        }
        this._teardownProxy();
        this._removeIndicator();
    }

    _onNameAppeared(connection, _name) {
        new FrameProxy(
            connection, BUS_NAME, OBJECT_PATH,
            (proxy, error) => {
                if (error) {
                    logError(error, 'frame: failed to create D-Bus proxy');
                    return;
                }
                this._proxy = proxy;
                this._signalId = proxy.connectSignal(
                    'StateChanged',
                    (_p, _sender, [recording, paused]) =>
                        this._update(recording, paused));
                // Sync current state immediately.
                proxy.GetStateRemote((result, err) => {
                    if (err) return;
                    const [recording, paused] = result;
                    this._update(recording, paused);
                });
            });
    }

    _onNameVanished(_connection, _name) {
        this._teardownProxy();
        this._update(false, false);
    }

    _teardownProxy() {
        if (this._proxy && this._signalId) {
            try {
                this._proxy.disconnectSignal(this._signalId);
            } catch (e) {
                // proxy may already be gone
            }
        }
        this._signalId = 0;
        this._proxy = null;
    }

    _update(recording, paused) {
        if (recording && !this._indicator)
            this._addIndicator();
        else if (!recording && this._indicator)
            this._removeIndicator();

        if (this._indicator)
            this._indicator.setPaused(paused);
    }

    _addIndicator() {
        this._indicator = new FrameIndicator({
            togglePause: () => this._call('TogglePause'),
            stop: () => this._call('Stop'),
        });
        Main.panel.addToStatusArea('frame', this._indicator, 0, 'right');
    }

    _removeIndicator() {
        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }

    _call(method) {
        if (!this._proxy) return;
        this._proxy[`${method}Remote`]((_r, err) => {
            if (err) logError(err, `frame: ${method} failed`);
        });
    }
}
