

from gi.repository import GdkPixbuf
from gi.repository import Gtk

from kuwo import Net
from kuwo import Widgets

class MV(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.app = app
        self.first_show = False

        self.buttonbox = Gtk.Box()
        self.pack_start(self.buttonbox, False, False, 0)
        button_home = Gtk.Button('MV')
        button_home.connect('clicked', self.on_button_home_clicked)
        self.buttonbox.pack_start(button_home, False, False, 0)
        self.label = Gtk.Label('')
        self.buttonbox.pack_start(self.label, False, False, 0)

        self.scrolled_nodes = Gtk.ScrolledWindow()
        self.pack_start(self.scrolled_nodes, True, True, 0)
        # logo, name, nid, info
        self.liststore_nodes = Gtk.ListStore(GdkPixbuf.Pixbuf, str, int, 
                str)
        iconview_nodes = Widgets.IconView(self.liststore_nodes)
        iconview_nodes.connect('item_activated', 
                self.on_iconview_nodes_item_activated)
        self.scrolled_nodes.add(iconview_nodes)

        self.scrolled_songs = Gtk.ScrolledWindow()
        self.pack_start(self.scrolled_songs, True, True, 0)
        # logo, name, artist, album, rid, artistid, albumid
        self.liststore_songs = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, 
                str, int, int, int)
        iconview_songs = Widgets.IconView(self.liststore_songs, info_pos=2)
        iconview_songs.connect('item_activated', 
                self.on_iconview_songs_item_activated)
        self.scrolled_songs.add(iconview_songs)

    def after_init(self):
        self.buttonbox.hide()
        self.scrolled_songs.hide()

    def first(self):
        if self.first_show:
            return
        self.first_show = True
        nid = 3
        nodes_wrap = Net.get_index_nodes(nid)
        if not nodes_wrap:
            return
        nodes = nodes_wrap['child']
        self.liststore_nodes.clear()
        i = 0
        for node in nodes:
            self.liststore_nodes.append([self.app.theme['anonymous'],
                node['disname'], int(node['sourceid']), node['info'], ])
            Net.update_liststore_image(self.liststore_nodes, i, 0,
                    node['pic'])
            i += 1

    def on_iconview_nodes_item_activated(self, iconview, path):
        model = iconview.get_model()
        self.buttonbox.show_all()
        self.label.set_label(model[path][1])
        self.scrolled_nodes.hide()
        self.scrolled_songs.show_all()
        self.curr_node_id = model[path][2]
        self.append_songs(init=True)

    def append_songs(self, init=False):
        def _append_songs(songs_args, error=None):
            songs, self.songs_total = songs_args
            if self.songs_total == 0:
                return
            i = len(self.liststore_songs)
            for song in songs:
                self.liststore_songs.append([self.app.theme['anonymous'],
                    song['name'], song['artist'], song['album'],
                    int(song['id']), int(song['artistid']), 
                    int(song['albumid']), ])
                Net.update_mv_image(self.liststore_songs, i, 0,
                        song['mvpic'])
                i += 1
            self.songs_page += 1
            if self.songs_page < self.songs_total - 1:
                self.append_songs()

        if init:
            self.songs_page = 0
            self.liststore_songs.clear()
        Net.async_call(Net.get_mv_songs, _append_songs, 
                self.curr_node_id, self.songs_page)

    def on_iconview_songs_item_activated(self, iconview, path):
        model = iconview.get_model()
        song = Widgets.song_row_to_dict(model[path])
        self.app.player.load_mv(song)

    def on_button_home_clicked(self, btn):
        self.scrolled_nodes.show_all()
        self.scrolled_songs.hide()
        self.buttonbox.hide()
