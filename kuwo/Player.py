

from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gst
from gi.repository import GstVideo
from gi.repository import Gtk
import time

from kuwo import Net
from kuwo import Widgets

# Gdk.EventType.2BUTTON_PRESS is an invalid variable
GDK_2BUTTON_PRESS = 5

#GObject.threads_init()
# init Gst so that play works ok.
Gst.init(None)


class PlayType:
    NONE = -1
    SONG = 0
    RADIO = 1
    MV = 2

def delta(nanosec_float):
    _seconds = nanosec_float // 10**9
    mm, ss = divmod(_seconds, 60)
    hh, mm = divmod(mm, 60)
    if hh == 0:
        s = '%d:%02d' % (mm, ss)
    else:
        s = '%d:%02d:%02d' % (hh, mm, ss)
    return s

class Player(Gtk.Box):
    def __init__(self, app):
        super().__init__()
        self.app = app

        self.fullscreen_sid = 0
        self.play_type = PlayType.NONE
        self.adj_timeout = 0
        self.recommend_imgs = None
        self.curr_song = None
        self.curr_mv_link = None

        self.playbin = Gst.ElementFactory.make('playbin', None)
        self.bus = self.playbin.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message::eos', self.on_eos)
        self.bus.connect('message::error', self.on_error)
        self.playbin.set_property('volume', app.conf['volume'])

        event_pic = Gtk.EventBox()
        event_pic.connect('button-press-event', self.on_pic_pressed)
        self.pack_start(event_pic, False, False, 0)

        self.artist_pic = Gtk.Image.new_from_pixbuf(app.theme['anonymous'])
        event_pic.add(self.artist_pic)

        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pack_start(control_box, True, True, 0)

        toolbar = Gtk.Toolbar()
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        toolbar.get_style_context().add_class(
                Gtk.STYLE_CLASS_PRIMARY_TOOLBAR)
        toolbar.set_show_arrow(False)
        toolbar.set_icon_size(5)
        control_box.pack_start(toolbar, False, False, 0)

        prev_button = Gtk.ToolButton()
        prev_button.set_label('Previous')
        prev_button.set_icon_name('media-skip-backward-symbolic')
        prev_button.connect('clicked', self.on_prev_button_clicked)
        toolbar.insert(prev_button, 0)

        self.play_button = Gtk.ToolButton()
        self.play_button.set_label('Play')
        self.play_button.set_icon_name('media-playback-start-symbolic')
        self.play_button.connect('clicked', self.on_play_button_clicked)
        toolbar.insert(self.play_button, 1)

        next_button = Gtk.ToolButton()
        next_button.set_label('Next')
        next_button.set_icon_name('media-skip-forward-symbolic')
        next_button.connect('clicked', self.on_next_button_clicked)
        toolbar.insert(next_button, 2)

        sep = Gtk.SeparatorToolItem()
        toolbar.insert(sep, 3)

        self.shuffle_btn = Gtk.ToggleToolButton()
        self.shuffle_btn.set_label('Shuffle')
        self.shuffle_btn.set_icon_name('media-playlist-shuffle-symbolic')
        toolbar.insert(self.shuffle_btn, 4)

        self.repeat_btn = Gtk.ToggleToolButton()
        self.repeat_btn.set_label('Repeat')
        self.repeat_btn.set_icon_name('media-playlist-repeat-symbolic')
        toolbar.insert(self.repeat_btn, 5)

        self.show_mv_btn = Gtk.ToggleToolButton()
        self.show_mv_btn.set_label('Show MV')
        self.show_mv_btn.set_icon_name('video-x-generic-symbolic')
        self.show_mv_btn.set_sensitive(False)
        self.show_mv_sid = self.show_mv_btn.connect('toggled', 
                self.on_show_mv_toggled)
        toolbar.insert(self.show_mv_btn, 6)

        self.fullscreen_btn = Gtk.ToolButton()
        self.fullscreen_btn.set_label('Fullscreen')
        self.fullscreen_btn.set_tooltip_text('Fullscreen (F11)')
        self.fullscreen_btn.set_icon_name('view-fullscreen-symbolic')
        # Does not work when in fullscreen.
        key, mod = Gtk.accelerator_parse('F11')
        self.fullscreen_btn.add_accelerator('clicked', app.accel_group,
                key, mod, Gtk.AccelFlags.VISIBLE)
        self.fullscreen_btn.connect('clicked', 
                self.on_fullscreen_button_clicked)
        toolbar.insert(self.fullscreen_btn, 7)

        self.label = Gtk.Label('<b>Unknown</b> <i>by unknown</i>')
        self.label.props.use_markup = True
        self.label.props.xalign = 0
        control_box.pack_start(self.label, False, False, 0)

        scale_box = Gtk.Box()
        control_box.pack_start(scale_box, True, False, 0)

        self.scale = Gtk.Scale()
        self.adjustment = Gtk.Adjustment(0, 0, 100, 1, 10, 0)
        self.scale.set_adjustment(self.adjustment)
        self.scale.props.draw_value = False
        self.scale.connect('change-value', self.on_scale_change_value)
        scale_box.pack_start(self.scale, True, True, 0)

        self.time_label = Gtk.Label('0:00/0:00')
        scale_box.pack_start(self.time_label, False, False, 0)

        self.volume = Gtk.VolumeButton()
        self.volume.props.use_symbolic = True
        self.volume.set_value(app.conf['volume'])
        self.volume.connect('value-changed', self.on_volume_value_changed)
        scale_box.pack_start(self.volume, False, False, 0)

    def after_init(self):
        pass

    def on_destroy(self):
        self.playbin.set_state(Gst.State.NULL)

    def load(self, song):
        def _on_chunk_received(widget, percent):
            pass

        def _on_song_can_play(widget, song_path):
            if song_path:
                GLib.idle_add(self._load_song, song_path)
            else:
                self.pause_player(stop=True)

        def _on_song_downloaded(widget, song_path):
            if song_path:
                GLib.idle_add(self.on_song_downloaded, song_path)

        self.play_type = PlayType.SONG
        self.curr_song = song
        self.pause_player(stop=True)
        parse_song = Net.AsyncSong(self.app)
        parse_song.connect('chunk-received', _on_chunk_received)
        parse_song.connect('can-play', _on_song_can_play)
        parse_song.connect('downloaded', _on_song_downloaded)
        parse_song.get_song(song)

    def _load_song(self, song_path):
        print('Player._load_song()', song_path)
        self.playbin.set_property('uri', 'file://' + song_path)
        self.start_player(load=True)
        self.app.lrc.show_music()
        self.update_player_info()
        self.get_lrc()
        self.show_mv_btn.set_sensitive(False)
        self.get_mv_link()
        self.get_recommend_lists()

    def on_song_downloaded(self, song_path):
        self.init_adjustment()
        self.scale.set_sensitive(True)
        if self.play_type == PlayType.SONG:
            self.app.playlist.on_song_downloaded(self.curr_song)

    def is_playing(self):
        state = self.playbin.get_state(5)
        return state[1] == Gst.State.PLAYING

    def init_adjustment(self):
        self.adjustment.set_value(0.0)
        self.adjustment.set_lower(0.0)
        # when song is not totally downloaded but can play, query_duration
        # might give incorrect/inaccurate result.
        status, upper = self.playbin.query_duration(Gst.Format.TIME)
        if status and upper > 0:
            self.adjustment.set_upper(upper)
            return False
        return True

    def sync_adjustment(self):
        status, curr = self.playbin.query_position(Gst.Format.TIME)
        if not status:
            return True
        status, total = self.playbin.query_duration(Gst.Format.TIME)
        self.adjustment.set_value(curr)
        self.adjustment.set_upper(total)
        self.sync_label_by_adjustment()
        if self.play_type == PlayType.MV:
            return True
        self.app.lrc.sync_lrc(curr)
        if self.recommend_imgs and len(self.recommend_imgs) > 0:
            # change lyrics background image every 20 seconds
            div, mod = divmod(int(curr / 10**9), 20)
            if mod == 0:
                div2, mod2 = divmod(div, len(self.recommend_imgs))
                self.update_lrc_background(self.recommend_imgs[mod2])
        return True

    def sync_label_by_adjustment(self):
        curr = delta(self.adjustment.get_value())
        total = delta(self.adjustment.get_upper())
        self.time_label.set_label('{0}/{1}'.format(curr, total))

    # Control panel
    def on_pic_pressed(self, eventbox, event):
        if event.type == GDK_2BUTTON_PRESS and \
                self.play_type == PlayType.SONG:
            self.app.playlist.locate_curr_song()

    def on_prev_button_clicked(self, button):
        if self.play_type == PlayType.RADIO:
            return
        _repeat = self.repeat_btn.get_active()
        _shuffle = self.shuffle_btn.get_active()
        # TODO: pause current song
        prev_song = self.app.playlist.get_prev_song(repeat=_repeat, 
                shuffle=_shuffle)
        if prev_song is not None:
            # TODO, FIXME: check PlayType
            self.load(prev_song)

    def on_play_button_clicked(self, button):
        if self.is_playing(): 
            self.pause_player()
        else:
            self.start_player()

    def start_player(self, load=False):
        self.play_button.set_icon_name('media-playback-pause-symbolic')
        self.playbin.set_state(Gst.State.PLAYING)
        self.adj_timeout = GLib.timeout_add(250, self.sync_adjustment)
        if load:
            GLib.timeout_add(1500, self.init_adjustment)

    def pause_player(self, stop=False):
        self.play_button.set_icon_name('media-playback-start-symbolic')
        if stop:
            self.playbin.set_state(Gst.State.NULL)
            self.scale.set_value(0)
            self.scale.set_sensitive(False)
            self.show_mv_btn.set_sensitive(False)
            self.show_mv_btn.handler_block(self.show_mv_sid)
            self.show_mv_btn.set_active(False)
            self.show_mv_btn.handler_unblock(self.show_mv_sid)
            self.time_label.set_label('0:00/0:00')
        else:
            self.playbin.set_state(Gst.State.PAUSED)
        if self.adj_timeout > 0:
            GLib.source_remove(self.adj_timeout)
            self.adj_timeout = 0

    def on_next_button_clicked(self, button):
        self.load_next()

    def load_next(self):
        # use EOS to load next song.
        self.on_eos(None, None)

    def on_scale_change_value(self, scale, scroll_type, value):
        '''
        When user move the scale, pause play and seek audio position.
        Delay 200 miliseconds to increase responce spead
        '''
        if self.play_type == PlayType.NONE:
            return
        self.pause_player()
        self.playbin.seek_simple(Gst.Format.TIME, 
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                self.adjustment.get_value())
        self.sync_label_by_adjustment()
        self.player_timestamp = time.time()
        GLib.timeout_add(200, self._delay_play, self.player_timestamp)

    def _delay_play(self, local_timestamp):
        if self.player_timestamp == local_timestamp:
            self.start_player()
        return False

    def on_volume_value_changed(self, volume, value):
        self.app.conf['volume'] = value
        self.playbin.set_property('volume', value)


    def update_player_info(self):
        def _update_pic(info, error=None):
            if info is None or error:
                return
            self.artist_pic.set_tooltip_text(
                    Widgets.short_tooltip(info['info'], length=500))
            if info['pic']:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_size(
                        info['pic'], 100, 100)
                self.artist_pic.set_from_pixbuf(pix)
            
        song = self.curr_song
        name = Widgets.short_tooltip(song['name'], 45)
        if len(song['artist']) > 0:
            artist = Widgets.short_tooltip(song['artist'], 20)
        else:
            artist = 'Unknown'
        if len(song['album']) > 0:
            album = Widgets.short_tooltip(song['album'], 30)
        else:
            album = 'Unknown'
        label = '<b>{0}</b> <i><small>by {1} from {2}</small></i>'.format(
                name, artist, album)
        self.label.set_label(label)
        self.artist_pic.set_from_pixbuf(self.app.theme['anonymous'])
        Net.async_call(Net.get_artist_info, _update_pic, 
                song['artistid'], song['artist'])

    def get_lrc(self):
        def _update_lrc(lrc_text, error=None):
            self.app.lrc.set_lrc(lrc_text)
        Net.async_call(Net.get_lrc, _update_lrc, self.curr_song['rid'])

    def get_recommend_lists(self):
        self.recommend_imgs = None
        def _on_list_received(imgs, error=None):
            if imgs is None or len(imgs) < 10:
                self.recommend_imgs = None
            else:
                self.recommend_imgs = imgs.splitlines()
        Net.async_call(Net.get_recommend_lists, _on_list_received, 
                self.curr_song['artist'])

    def update_lrc_background(self, url):
        def _update_background(filepath, error=None):
            if filepath:
                self.app.lrc.update_background(filepath)
        Net.async_call(Net.get_recommend_image, _update_background, url)

    def on_eos(self, bus, msg):
        '''
        When EOS is reached, try to fetch next song.
        '''
        self.pause_player(stop=True)
        _repeat = self.repeat_btn.get_active()
        _shuffle = self.shuffle_btn.get_active()
        if self.play_type == PlayType.RADIO:
            self.curr_radio_item.play_next_song()
        elif self.play_type == PlayType.SONG:
            next_song = self.app.playlist.get_next_song(repeat=_repeat, 
                    shuffle=_shuffle)
            print('next song:', next_song)
            if next_song is not None:
                self.load(next_song)

    def on_error(self, bus, msg):
        print('on_error():', msg.parse_error())

    # Radio part
    def load_radio(self, song, radio_item):
        '''
        song from radio, only contains name, artist, rid, artistid
        Remember to update its information.
        '''
        def _on_radio_can_play(widget, song):
            GLib.idle_add(self._load_song, song)

        def _on_radio_downloaded(*args):
            self.scale.set_sensitive(True)
            self.curr_radio_item.cache_next_song()

        self.play_type = PlayType.RADIO
        self.pause_player(stop=True)
        self.curr_radio_item = radio_item
        self.curr_song = song
        self.scale.set_sensitive(False)
        parse_song = Net.AsyncSong(self.app)
        parse_song.connect('can-play', _on_radio_can_play)
        parse_song.connect('downloaded', _on_radio_downloaded)
        parse_song.get_song(song)


    # MV part
    def on_show_mv_toggled(self, toggle_button):
        if self.play_type == PlayType.NONE:
            toggle_button.set_active(False)
            return
        state = toggle_button.get_active()
        if state:
            self.app.lrc.show_mv()
            self.enable_bus_sync()
            self.load_mv(self.curr_song)
        else:
            self.app.lrc.show_music()
            self.load(self.curr_song)
            # TODO, FIXME
            #self.disable_bus_sync()

    def load_mv(self, song):
        self.play_type = PlayType.MV
        self.curr_song = song
        self.pause_player(stop=True)
        self.show_mv_btn.set_sensitive(True)
        self.show_mv_btn.handler_block(self.show_mv_sid)
        self.show_mv_btn.set_active(True)
        self.show_mv_btn.handler_unblock(self.show_mv_sid)
        self.get_mv_link()

    def _load_mv(self, mv_path):
        self.playbin.set_property('uri', 'file://' + mv_path)
        self.app.lrc.show_mv()
        self.enable_bus_sync()
        self.start_player(load=True)
        self.update_player_info()

    def on_mv_can_play(self, widget, mv_path):
        if mv_path:
            GLib.idle_add(self._load_mv, mv_path)
        else:
            # Failed to download MV,
            self.pause_player(stop=True)

    def on_mv_downloaded(self, widget, mv_path):
        self.scale.set_sensitive(True)

    def get_mv_link(self):
        def _update_mv_link(mv_link, error=None):
            self.show_mv_btn.set_sensitive(mv_link is not None)
            if mv_link is None:
                return
            self.curr_mv_link = mv_link
            if self.play_type == PlayType.MV:
                parse_mv = Net.AsyncMV(self.app)
                parse_mv.connect('can-play', self.on_mv_can_play)
                parse_mv.connect('downloaded', self.on_mv_downloaded)
                parse_mv.get_mv(mv_link)

        Net.async_call(Net.get_song_link, _update_mv_link,
                # rid, use-mkv, use-mv
                self.curr_song['rid'], self.app.conf['use-mkv'], True)

    def enable_bus_sync(self):
        self.bus.enable_sync_message_emission()
        self.bus_sync_sid = self.bus.connect('sync-message::element', 
                self.on_sync_message)

    def disable_bus_sync(self):
        self.bus.disconnect(self.bus_sync_sid)
        self.bus.disable_sync_message_emission()

    def on_sync_message(self, bus, msg):
        if msg.get_structure().get_name() == 'prepare-window-handle':
            #print('prepare-window-handle')
            msg.src.set_window_handle(self.app.lrc.xid)


    # Fullscreen
    def on_fullscreen_button_clicked(self, button):
        print('on fullscreen button clicked')
        print('fullscreen_sid:', self.fullscreen_sid)
        window = self.app.window
        if self.fullscreen_sid > 0:
            button.set_icon_name('view-fullscreen-symbolic')
            window.realize()
            window.unfullscreen()
            window.disconnect(self.fullscreen_sid)
            self.fullscreen_sid = 0
        else:
            button.set_icon_name('view-restore-symbolic')
            self.app.notebook.set_show_tabs(False)
            self.hide()
            window.realize()
            window.fullscreen()
            self.fullscreen_sid = window.connect('motion-notify-event',
                    self.on_window_motion_notified)

    def on_window_motion_notified(self, *args):
        # show control_panel and notebook label
        self.show_all()
        self.app.notebook.set_show_tabs(True)
        # delay 3 seconds to hide them
        self.fullscreen_timestamp = time.time()
        GLib.timeout_add(3000, self.hide_control_panel_and_label, 
                self.fullscreen_timestamp)

    def hide_control_panel_and_label(self, timestamp):
        if timestamp == self.fullscreen_timestamp and \
                self.fullscreen_sid > 0:
            self.app.notebook.set_show_tabs(False)
            self.hide()
