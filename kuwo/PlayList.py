
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk
import json
import os
import random
import shutil
import sqlite3
import threading
import time

from kuwo import Config
from kuwo import Net
from kuwo import Widgets

_ = Config._


class NormalSongTab(Gtk.ScrolledWindow):
    def __init__(self, app, list_name):
        super().__init__()
        self.app = app
        self.list_name = list_name

        # name, artist, album, rid, artistid, albumid
        self.liststore = Gtk.ListStore(str, str, str, int, int, int)

        self.treeview = Gtk.TreeView(model=self.liststore)
        self.treeview.set_headers_visible(False)
        self.treeview.set_search_column(0)
        self.treeview.props.reorderable = True
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.treeview.connect('row_activated', 
                self.on_treeview_row_activated)
        self.add(self.treeview)

        song_name = Gtk.CellRendererText()
        col_song = Widgets.TreeViewColumnText('Name', song_name, text=0)
        self.treeview.append_column(col_song)

        artist = Gtk.CellRendererText()
        col_artist = Widgets.TreeViewColumnText('Aritst', artist, text=1)
        self.treeview.append_column(col_artist)

        album = Gtk.CellRendererText()
        col_album = Widgets.TreeViewColumnText('Album', album, text=2)
        self.treeview.append_column(col_album)

        if list_name != 'Cached':
            delete = Gtk.CellRendererPixbuf(icon_name='user-trash-symbolic')
            col_delete = Widgets.TreeViewColumnIcon('Delete', delete)
            self.treeview.append_column(col_delete)
            self.connect('key-press-event', self.on_key_pressed)
        
    def on_key_pressed(self, widget, event):
        if event.keyval == Gdk.KEY_Delete:
            selection = self.treeview.get_selection()
            model, paths = selection.get_selected_rows()
            # paths needs to be reversed, or else an IndexError throwed.
            for path in reversed(paths):
                model.remove(model[path].iter)

    def on_treeview_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        index = treeview.get_columns().index(column)
        song = Widgets.song_row_to_dict(model[path], start=0)
        if index == 0:
            self.app.playlist.play_song(song, list_name=self.list_name)
        elif index == 1:
            self.app.search.search_artist(song['artist'])
        elif index == 2:
            self.app.search.search_album(song['album'])
        elif index == 3:
            model.remove(model[path].iter)

class PlayList(Gtk.Box):
    def __init__(self, app):
        super().__init__()

        self.app = app
        self.first_show = False
        self.tabs = {}
        # self.lists_name contains playlists name
        self.lists_name = []
        # use curr_playing to locate song in treeview
        self.curr_playing = [None, None]

        self.cache_enabled = False
        self.cache_job = None
        self.cache_timeout = 0

        self.cache_next_async_song = None

        #self.playlist_menu_model = Gio.Menu()
        self.playlist_menu = Gtk.Menu()

        self.conn = sqlite3.connect(Config.SONG_DB)
        self.cursor = self.conn.cursor()

        box_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pack_start(box_left, False, False, 0)

        # disname, name/uuid, deletable/editable
        self.liststore_left = Gtk.ListStore(str, str, bool)
        self.treeview_left = Gtk.TreeView(model=self.liststore_left)
        self.treeview_left.set_headers_visible(False)
        list_disname = Gtk.CellRendererText()
        list_disname.connect('edited', self.on_list_disname_edited)
        col_name = Gtk.TreeViewColumn('List Name', list_disname, 
                text=0, editable=2)
        self.treeview_left.append_column(col_name)
        tree_sel = self.treeview_left.get_selection()
        tree_sel.connect('changed', self.on_tree_selection_left_changed)
        box_left.pack_start(self.treeview_left, True, True, 0)

        toolbar = Gtk.Toolbar()
        toolbar.get_style_context().add_class(
                Gtk.STYLE_CLASS_INLINE_TOOLBAR)
        toolbar.props.show_arrow = False
        toolbar.props.toolbar_style = Gtk.ToolbarStyle.ICONS
        toolbar.props.icon_size = 1
        add_btn = Gtk.ToolButton()
        add_btn.set_name('Add')
        add_btn.set_icon_name('list-add-symbolic')
        add_btn.connect('clicked', self.on_add_playlist_button_clicked)
        toolbar.insert(add_btn, 0)
        remove_btn = Gtk.ToolButton()
        remove_btn.set_name('Remove')
        remove_btn.set_icon_name('list-remove-symbolic')
        remove_btn.connect('clicked', 
                self.on_remove_playlist_button_clicked)
        toolbar.insert(remove_btn, 1)
        export_btn = Gtk.ToolButton()
        export_btn.set_name('Export')
        export_btn.set_icon_name('media-eject-symbolic')
        export_btn.connect('clicked', 
                self.on_export_playlist_button_clicked)
        toolbar.insert(export_btn, 2)
        box_left.pack_start(toolbar, False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.props.show_tabs = False
        self.pack_start(self.notebook, True, True, 0)

        # Use this trick to accelerate startup speed of app.
        GLib.timeout_add(1500, self.init_ui)

    def do_destroy(self):
        print('Playlist.do_destroy()')
        self.conn.commit()
        self.conn.close()
        self.dump_playlists()
        if self.cache_job:
            self.cache_job.destroy()
        if self.cache_next_async_song:
            self.cache_next_async_song.destroy()

    def after_init(self):
        pass

    def first(self):
        pass

    def init_ui(self):
        self.init_table()
        self.load_playlists()
        return False

    def init_table(self):
        sql = '''
        CREATE TABLE IF NOT EXISTS `songs` (
        name CHAR,
        artist CHAR,
        album CHAR,
        rid INTEGER,
        artistid INTEGER,
        albumid INTEGER
        )
        '''
        self.cursor.execute(sql)
        self.conn.commit()

    def dump_playlists(self):
        filepath = Config.PLS_JSON
        names = [list(p) for p in self.liststore_left]
        playlists = {'_names_': names}
        for name in names:
            list_name = name[1]
            if list_name == 'Cached':
                continue
            liststore = self.tabs[list_name].liststore
            playlists[list_name] = [list(p) for p in liststore]
        with open(filepath, 'w') as fh:
            fh.write(json.dumps(playlists))

    def load_playlists(self):
        filepath = Config.PLS_JSON
        _default = {
                '_names_': [
                    [_('Cached'), 'Cached', False],
                    [_('Caching'), 'Caching', False],
                    [_('Default'), 'Default', False],
                    [_('Favorite'), 'Favorite', False],
                    ],
                'Caching': [],
                'Default': [],
                'Favorite': [],
                }
        if os.path.exists(filepath):
            with open(filepath) as fh:
                playlists = json.loads(fh.read())
        else:
            playlists = _default

        for playlist in playlists['_names_']:
            self.liststore_left.append(playlist)
            disname, list_name, editable = playlist
            if list_name == 'Cached':
                songs = self.get_all_cached_songs_from_db()
            else:
                songs = playlists[list_name]
            if list_name not in ('Cached', 'Caching'):
                self.append_menu_item_to_playlist_menu(disname, list_name)
            self.init_tab(list_name, songs)

    def init_tab(self, list_name, songs):
        scrolled_win = NormalSongTab(self.app, list_name)
        for song in songs:
            scrolled_win.liststore.append(song)
        if list_name == 'Caching':
            box_caching = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            buttonbox = Gtk.Box()
            box_caching.pack_start(buttonbox, False, False, 0)
            button_start = Gtk.Button(_('Start Caching'))
            button_start.connect('clicked', self.switch_caching_daemon)
            buttonbox.pack_start(button_start, False, False, 0)
            box_caching.pack_start(scrolled_win, True, True, 0)
            self.notebook.append_page(box_caching, Gtk.Label(_('Caching')))
            box_caching.show_all()
        else:
            self.notebook.append_page(scrolled_win, Gtk.Label(list_name))
            scrolled_win.show_all()
        self.tabs[list_name] = scrolled_win

    # Side Panel
    def on_tree_selection_left_changed(self, tree_sel):
        model, tree_iter = tree_sel.get_selected()
        path = model.get_path(tree_iter)
        index = path.get_indices()[0]
        self.notebook.set_current_page(index)

    # Open API for others to call.
    def play_song(self, song, list_name='Default'):
        if not song:
            return
        liststore = self.tabs[list_name].liststore
        rid = song['rid']
        path = self.get_song_path_in_liststore(liststore, rid)
        if path is not None:
            # curr_playing contains: listname, path
            self.curr_playing = [list_name, path]
            song = Widgets.song_row_to_dict(liststore[path], start=0)
            self.app.player.load(song)
            return
        liststore.append(Widgets.song_dict_to_row(song))
        self.curr_playing = [list_name, len(liststore)-1, ]
        self.app.player.load(song)

    def play_songs(self, songs):
        if not songs or len(songs) == 0:
            return
        self.add_songs_to_playlist(songs, list_name='Default')
        self.play_song(songs[0])

    def add_song_to_playlist(self, song, list_name='Default'):
        liststore = self.tabs[list_name].liststore
        rid = song['rid']
        path = self.get_song_path_in_liststore(liststore, rid)
        if path is not None:
            return
        liststore.append(Widgets.song_dict_to_row(song))

    def add_songs_to_playlist(self, songs, list_name='Default'):
        print('PlayList.add_songs_to_playlist()')
        for song in songs:
            self.add_song_to_playlist(song, list_name=list_name)

    def cache_song(self, song):
        rid = song['rid']
        # first, check if this song exists in cached_db
        req = self.get_song_from_cached_db(rid)
        if req is not None:
            print('local cache exists, quit')
            return
        # second, check song in caching_liststore.
        liststore = self.tabs['Caching'].liststore
        path = self.get_song_path_in_liststore(liststore, rid)
        if path is not None:
            print('song is already in caching list, do nothing.')
            return
        liststore.append(Widgets.song_dict_to_row(song))

    def cache_songs(self, songs):
        for song in songs:
            self.cache_song(song)

    # song cache daemon
    def switch_caching_daemon(self, btn):
        print('switch caching daemon')
        if not self.cache_enabled:
            self.cache_enabled = True
            btn.set_label(_('Stop Caching'))
            self.cache_timeout = GLib.timeout_add(5000, 
                    self.start_cache_daemon)
        else:
            self.cache_enabled = False
            if self.cache_timeout > 0:
                GLib.source_remove(self.cache_timeout)
            btn.set_label(_('Start Caching'))

    def start_cache_daemon(self):
        if self.cache_enabled:
            if self.cache_job is None:
                self.do_cache_song_pool()
            return True
        else:
            return False

    def do_cache_song_pool(self):
        def _move_song():
            self.append_cached_song(song)
            liststore.remove(liststore[path].iter)
            Gdk.Window.process_all_updates()

        def _on_downloaded(widget, song_path, error=None):
            self.cache_job = None
            GLib.idle_add(_move_song)

        list_name = 'Caching'
        liststore = self.tabs[list_name].liststore
        path = 0
        if len(liststore) == 0:
            print('Caching playlist is empty, please add some')
            return
        song = Widgets.song_row_to_dict(liststore[path], start=0)
        print('song dict to download:', song)
        self.cache_job = Net.AsyncSong(self.app)
        self.cache_job.connect('downloaded', _on_downloaded)
        self.cache_job.get_song(song)

    # Others
    def on_song_downloaded(self, play=False):
        # copy this song from current playing list to cached_list.
        list_name = self.curr_playing[0]
        liststore = self.tabs[list_name].liststore
        path = self.curr_playing[1]
        song = Widgets.song_row_to_dict(liststore[path], start=0)
        self.append_cached_song(song)
        Gdk.Window.process_all_updates()

    def cache_next_song(self):
        list_name = self.curr_playing[0]
        liststore = self.tabs[list_name].liststore
        path = self.curr_playing[1]
        if path == len(liststore) - 1:
            return
        path += 1
        song = Widgets.song_row_to_dict(liststore[path], start=0)
        print('next song to cache:', song)
        self.cache_next_async_song = Net.AsyncSong(self.app)
        self.cache_next_async_song.get_song(song)

    def get_prev_song(self, repeat=False, shuffle=False):
        print('get prev song()')
        list_name = self.curr_playing[0]
        if list_name is None:
            return
        liststore = self.tabs[list_name].liststore
        path = self.curr_playing[1]
        song_nums = len(liststore)
        if song_nums == 0:
            return None
        if shuffle:
            path = random.randint(0, song_nums-1)
        elif path == 0:
            # Already reach top of the list, maybe we can repeat from bottom
            path = 0
        else:
            path = path - 1
        self.curr_playing[1] = path
        return Widgets.song_row_to_dict(liststore[path], start=0)

    def get_next_song(self, repeat=False, shuffle=False):
        print('get next song()')
        list_name = self.curr_playing[0]
        liststore = self.tabs[list_name].liststore
        path = self.curr_playing[1]
        song_nums = len(liststore)
        if song_nums == 0:
            return None

        if shuffle:
            path = random.randint(0, song_nums-1)
        elif path == song_nums - 1:
            if repeat is False:
                return None
            # repeat from the first song
            path = 0
        else:
            path = path + 1
        self.curr_playing[1] = path
        return Widgets.song_row_to_dict(liststore[path], start=0)

    def locate_curr_song(self):
        '''
        switch current playlist and select curr_song
        '''
        list_name = self.curr_playing[0]
        if list_name is None:
            return
        treeview = self.tabs[list_name].treeview
        liststore = treeview.get_model()
        path = self.curr_playing[1]
        treeview.set_cursor(path)

        left_path = 0
        for item in self.liststore_left:
            if list_name == self.liststore_left[left_path][1]:
                break
            left_path += 1
        selection_left = self.treeview_left.get_selection()
        selection_left.select_path(left_path)

    # DB operations
    def append_cached_song(self, song):
        '''
        When a new song is cached locally, call this function.
        Insert a new item to database and liststore_cached.
        '''
        # check this song already exists.
        req = self.get_song_from_cached_db(song['rid'])
        if req:
            return
        song_list = Widgets.song_dict_to_row(song)
        sql = 'INSERT INTO `songs` values(?, ?, ?, ?, ?, ?)'
        self.cursor.execute(sql, song_list)
        self.tabs['Cached'].liststore.append(song_list)

    def get_all_cached_songs_from_db(self):
        # TODO: use scrollbar to dynamically load.
        sql = 'SELECT * FROM `songs`'
        result = self.cursor.execute(sql)
        return result

    def get_song_from_cached_db(self, rid):
        sql = 'SELECT * FROM `songs` WHERE rid=? LIMIT 1'
        result = self.cursor.execute(sql, (rid, ))
        return result.fetchone()

    def get_song_path_in_liststore(self, liststore, rid, pos=3):
        i = 0
        for item in liststore:
            if item[pos] == rid:
                return i
            i += 1
        return None


    # left panel
    def on_list_disname_edited(self, cell, path, new_name):
        if len(new_name) == 0:
            return
        old_name = self.liststore_left[path][0]
        self.liststore_left[path][0] = new_name
        self.update_item_name_in_playlist_menu(old_name, new_name)

    def on_add_playlist_button_clicked(self, button):
        list_name = str(time.time())
        disname = _('Playlist')
        editable = True
        _iter = self.liststore_left.append([disname, list_name, editable])
        selection = self.treeview_left.get_selection()
        selection.select_iter(_iter)
        self.init_tab(list_name, [])
        self.append_menu_item_to_playlist_menu(disname, list_name)

    def on_remove_playlist_button_clicked(self, button):
        selection = self.treeview_left.get_selection()
        model, _iter = selection.get_selected()
        if not _iter:
            return
        path = model.get_path(_iter)
        index = path.get_indices()[0]
        disname, list_name, editable = model[path]
        if not editable:
            return
        self.notebook.remove_page(index)
        model.remove(_iter)
        self.remove_menu_item_from_playlist_menu(disname)

    def on_export_playlist_button_clicked(self, button):
        def do_export(button):
            num_songs = len(liststore)
            i = 0
            for item in liststore:
                name = item[0]
                artist = item[1]
                album = item[2]
                rid = item[3]
                song_link = Net.get_song_link(rid)
                song_name = os.path.split(song_link)[1]
                song_path = os.path.join(self.app.conf['song-dir'], 
                        song_name)
                if not os.path.exists(song_path):
                    continue
                export_song_name = '{0}_{1}{2}'.format(name, artist, 
                        os.path.splitext(song_name)[1]).replace('/', '+')
                export_song_path = os.path.join(
                        folder_chooser.get_filename(), export_song_name)
                i += 1
                shutil.copy(song_path, export_song_path)
                export_prog.set_fraction(i / num_songs)
                Gdk.Window.process_all_updates()
            dialog.destroy()

        selection = self.treeview_left.get_selection()
        model, _iter = selection.get_selected()
        if not _iter:
            return
        path = model.get_path(_iter)
        index = path.get_indices()[0]
        disname, list_name, editable = model[path]
        liststore = self.tabs[list_name].liststore

        dialog = Gtk.Dialog(_('Export Songs'), self.app.window,
                Gtk.DialogFlags.MODAL,
                (Gtk.STOCK_CLOSE, Gtk.ResponseType.OK,))
        box = dialog.get_content_area()
        box.set_size_request(600, 320)
        box.set_border_width(5)

        folder_label = Widgets.BoldLabel(_('Choose export folder'))
        box.pack_start(folder_label, False, True, 0)

        folder_chooser = Widgets.FolderChooser(self.app.window)
        box.pack_start(folder_chooser, False, True, 0)

        export_box = Gtk.Box(spacing=5)
        export_box.props.margin_top = 20
        box.pack_start(export_box, False, True, 0)

        export_prog = Gtk.ProgressBar()
        export_box.pack_start(export_prog, True, True, 0)

        export_btn = Gtk.Button(_('Export'))
        export_btn.connect('clicked', do_export)
        export_box.pack_start(export_btn, False, False, 0)

        infobar = Gtk.InfoBar()
        infobar.props.margin_top = 20
        box.pack_start(infobar, False, True, 0)
        info_content = infobar.get_content_area()
        info_label = Gtk.Label(_('Only cached songs will be exported'))
        info_content.pack_start(info_label, False, False, 0)

        box.show_all()
        dialog.run()
        dialog.destroy()

    # other button can activate this function
    def append_menu_item_to_playlist_menu(self, disname, list_name):
        menu_item = Gtk.MenuItem(disname)
        menu_item.connect('activate', self.on_menu_item_active)
        menu_item.list_name = list_name
        self.playlist_menu.append(menu_item)

    def remove_menu_item_from_playlist_menu(self, disname):
        item = self.get_item_from_playlist_menu(disname)
        self.playlist_menu.remove(item)

    def update_item_name_in_playlist_menu(self, old_name, new_name):
        item = self.get_item_from_playlist_menu(old_name)
        item.set_label(new_name)

    def get_item_from_playlist_menu(self, disname):
        menu = self.playlist_menu
        items = menu.get_children()
        for item in items:
            if item.get_label() == disname:
                return item

    def on_menu_item_active(self, menu_item):
        list_name = menu_item.list_name
        songs = self.playlist_menu.songs
        self.add_songs_to_playlist(songs, list_name)

    def popup_playlist_menu(self, button, songs):
        def set_pos(menu, user_data=None):
            event = Gtk.get_current_event().button
            alloc = button.get_allocation()
            return (event.x, event.y + alloc.height, True)

        menu = self.playlist_menu
        menu.songs = songs
        menu.show_all()
        menu.popup(None, None, None, None, 1, 
                Gtk.get_current_event_time())
