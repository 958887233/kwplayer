
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango
import os
import shutil

from kuwo import Config


MARGIN_LEFT = 15
MARGIN_TOP = 20

class NoteTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_border_width(10)


class BoldLabel(Gtk.Label):
    def __init__(self, label):
        super().__init__(label)
        self.set_use_markup(True)
        self.props.halign = Gtk.Align.START
        self.props.xalign = 0
        self.props.margin_bottom = 10

class ChooseFolder(Gtk.Box):
    def __init__(self, parent, conf_name, toggle_label):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.props.margin_left = MARGIN_LEFT
        self.parent = parent
        self.app = parent.app
        self.conf_name = conf_name
        self.old_dir = self.app.conf[conf_name]

        hbox = Gtk.Box(spacing=5)
        self.pack_start(hbox, False, True, 0)

        self.dir_entry = Gtk.Entry()
        self.dir_entry.set_text(self.old_dir)
        self.dir_entry.props.editable = False
        self.dir_entry.props.width_chars = 20
        hbox.pack_start(self.dir_entry, True, True, 0)

        choose_button = Gtk.Button('...')
        choose_button.connect('clicked', self.on_choose_button_clicked)
        hbox.pack_start(choose_button, False, False, 0)

        self.check_button = Gtk.CheckButton(toggle_label)
        self.check_button.set_active(True)
        self.check_button.props.halign = Gtk.Align.START
        self.check_button.connect('toggled', self.on_check_button_toggled)
        self.pack_start(self.check_button, False, False, 0)

        self.progress_bar = Gtk.ProgressBar()
        self.pack_start(self.progress_bar, False, False, 0)

    def on_choose_button_clicked(self, button):
        def on_dialog_file_activated(dialog):
            new_dir = dialog.get_filename()
            dialog.destroy()
            self.dir_entry.set_text(new_dir)
            self.app.conf[self.conf_name] = new_dir
            GLib.timeout_add(500, self.move_items, new_dir)
            return

        dialog = Gtk.FileChooserDialog('Choose a Folder', self.parent,
                Gtk.FileChooserAction.SELECT_FOLDER,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_OK, Gtk.ResponseType.OK))

        dialog.connect('file-activated', on_dialog_file_activated)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            on_dialog_file_activated(dialog)
            return
        dialog.destroy()

    def move_items(self, new_dir):
        status = self.check_button.get_active()
        if not status:
            self.old_dir = new_dir
            return False
        self.app.player.pause_player(stop=True)
        items = os.listdir(self.old_dir)
        self.progress_bar.set_fraction(0)
        length = len(items)
        i = 0
        Gdk.Window.process_all_updates()
        for item in items:
            shutil.move(os.path.join(self.old_dir, item),
                    os.path.join(new_dir, item))
            i += 1
            self.progress_bar.set_fraction(i / length)
            Gdk.Window.process_all_updates()
        self.old_dir = new_dir
        return False

    def on_check_button_toggled(self, toggle):
        status = toggle.get_active()
        if status:
            self.progress_bar.show_all()
        else:
            self.progress_bar.hide()


class Preferences(Gtk.Dialog):
    def __init__(self, app):
        super().__init__('Preferences', app.window, 0,
                (Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE,))
        self.app = app
        self.set_default_size(600, 320)
        self.set_border_width(5)
        box = self.get_content_area()
        #box.props.margin_left = MARGIN_LEFT

        notebook = Gtk.Notebook()
        box.pack_start(notebook, True, True, 0)

        # format tab
        format_box = NoteTab()
        notebook.append_page(format_box, Gtk.Label('Format'))

        audio_label = BoldLabel('<b>Prefered Audio Format</b>')
        format_box.pack_start(audio_label, False, False, 0)
        radio_mp3 = Gtk.RadioButton('MP3 (faster)')
        radio_mp3.props.margin_left = MARGIN_LEFT
        radio_mp3.connect('toggled', self.on_audio_toggled)
        format_box.pack_start(radio_mp3, False, False, 0)
        radio_ape = Gtk.RadioButton('APE (better)')
        radio_ape.join_group(radio_mp3)
        radio_ape.props.margin_left = MARGIN_LEFT
        radio_ape.set_active(app.conf['use-ape'])
        radio_ape.connect('toggled', self.on_audio_toggled)
        format_box.pack_start(radio_ape, False, False, 0)

        video_label = BoldLabel('<b>Prefered Video Format</b>')
        video_label.props.margin_top = MARGIN_TOP
        format_box.pack_start(video_label, False, False, 0)
        radio_mp4 = Gtk.RadioButton('MP4 (faster)')
        radio_mp4.props.margin_left = MARGIN_LEFT
        radio_mp4.connect('toggled', self.on_video_toggled)
        format_box.pack_start(radio_mp4, False, False, 0)
        radio_mkv = Gtk.RadioButton('MKV (better)')
        radio_mkv.props.margin_left = MARGIN_LEFT
        radio_mkv.join_group(radio_mp4)
        radio_mkv.set_active(app.conf['use-mkv'])
        radio_mkv.connect('toggled', self.on_video_toggled)
        format_box.pack_start(radio_mkv, False, False, 0)

        # lyrics tab
        lrc_box = NoteTab()
        notebook.append_page(lrc_box, Gtk.Label('Lyrics'))

        lrc_word_back_color_box = Gtk.Box()
        lrc_box.pack_start(lrc_word_back_color_box, False, False, 0)

        lrc_word_back_color_label = BoldLabel(
                '<b>Lyric Word Background color</b>')
        lrc_word_back_color_box.pack_start(lrc_word_back_color_label, 
                False, False, 0)

        lrc_word_back_color = Gtk.ColorButton()
        lrc_word_back_color.set_use_alpha(True)
        lrc_word_back_rgba = Gdk.RGBA()
        lrc_word_back_rgba.parse(app.conf['lrc-word-back-color'])
        lrc_word_back_color.set_rgba(lrc_word_back_rgba)
        lrc_word_back_color.connect('color-set',
                self.on_lrc_word_back_color_set)
        lrc_word_back_color.set_title('Choose color for Lyrics background')
        lrc_word_back_color_box.pack_start(lrc_word_back_color,
                False, False, 20)
        
        lrc_img_back_color_box = Gtk.Box()
        lrc_box.pack_start(lrc_img_back_color_box, False, False, 0)

        lrc_img_back_color_label = BoldLabel(
                '<b>Lyric Image Background color</b>')
        lrc_img_back_color_box.pack_start(lrc_img_back_color_label,
                False, False, 0)

        lrc_img_back_color = Gtk.ColorButton()
        lrc_img_back_color.set_use_alpha(True)
        lrc_img_back_rgba = Gdk.RGBA()
        lrc_img_back_rgba.parse(app.conf['lrc-img-back-color'])
        lrc_img_back_color.set_rgba(lrc_img_back_rgba)
        lrc_img_back_color.connect('color-set', 
                self.on_lrc_img_back_color_set)
        lrc_img_back_color.set_title('Choose color for Lyrics background')
        lrc_img_back_color_box.pack_start(lrc_img_back_color,
                False, False, 20)
        
        # folders tab
        folder_box = NoteTab()
        notebook.append_page(folder_box, Gtk.Label('Folders'))

        song_folder_label = BoldLabel('<b>Place to store sogns</b>')
        folder_box.pack_start(song_folder_label, False, False, 0)
        song_folder = ChooseFolder(self, 'song-dir', 
                'Moving cached songs to new folder')
        folder_box.pack_start(song_folder, False, False, 0)

        mv_folder_label = BoldLabel('<b>Place to store MVs</b>')
        mv_folder_label.props.margin_top = MARGIN_TOP
        folder_box.pack_start(mv_folder_label, False, False, 0)
        mv_folder = ChooseFolder(self, 'mv-dir',
                'Moving cached MVs to new folder')
        folder_box.pack_start(mv_folder, False, False, 0)

    def run(self):
        self.get_content_area().show_all()
        super().run()

    def on_destroy(self):
        print('dialog.on_destroy()')
        Config.dump_conf(self.app.conf)

    def on_audio_toggled(self, radiobtn):
        self.app.conf['use-ape'] = radiobtn.get_group()[0].get_active()

    def on_video_toggled(self, radiobtn):
        # radio_group[0] is MKV
        self.app.conf['use-mkv'] = radiobtn.get_group()[0].get_active()

    def on_lrc_word_back_color_set(self, colorbutton):
        back_rgba = colorbutton.get_rgba()
        # Fixed: if alpha == 1, to_string() will remove alpha value
        #        and we got a RGB instead of RGBA.
        if back_rgba.alpha == 1:
            back_rgba.alpha = 0.999
        back_rgba.to_string()
        self.app.conf['lrc-word-back-color'] = back_rgba.to_string()

    def on_lrc_img_back_color_set(self, colorbutton):
        back_rgba = colorbutton.get_rgba()
        if back_rgba.alpha == 1:
            back_rgba.alpha = 0.999
        back_rgba.to_string()
        self.app.conf['lrc-img-back-color'] = back_rgba.to_string()
