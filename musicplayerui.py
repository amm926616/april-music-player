import json
from base64 import b64decode
import os
import sys
import platform
from PyQt6.QtGui import QAction, QIcon, QFont, QFontDatabase, QAction, QCursor, QKeyEvent, QActionGroup, QColor, \
    QPainter, QPixmap, QPainterPath, QTextDocument
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QMessageBox, QSystemTrayIcon, QMenu, QWidgetAction,
    QLabel, QPushButton, QSlider, QLineEdit, QTableWidget, QFileDialog, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QCoreApplication, QRectF
from mutagen import File
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.oggvorbis import OggVorbis
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE
from album_image_window import AlbumImageWindow
from lrcsync import LRCSync
from musicplayer import MusicPlayer
from clickable_label import ClickableLabel
from easy_json import EasyJson
from songtablewidget import SongTableWidget
from albumtreewidget import AlbumTreeWidget
from random import choice, shuffle
from fontsettingdialog import FontSettingsWindow
from tag_dialog import TagDialog
from addnewdirectory import AddNewDirectory


def html_to_plain_text(html):
    doc = QTextDocument()
    doc.setHtml(html)
    return doc.toPlainText()


def extract_mp3_album_art(audio_file):
    """Extract album art from an MP3 file."""
    if audio_file.tags is None:
        return None

    for tag in audio_file.tags.values():
        if isinstance(tag, APIC):
            return tag.data
    return None


def extract_mp4_album_art(audio_file):
    """Extract album art from an MP4 file."""
    covers = audio_file.tags.get('covr')
    if covers:
        return covers[0] if isinstance(covers[0], bytes) else covers[0].data
    return None


def extract_flac_album_art(audio_file):
    """Extract album art from a FLAC file."""
    if audio_file.pictures:
        return audio_file.pictures[0].data
    return None


def extract_ogg_album_art(audio_file):
    """Extract album art from an OGG file."""
    if 'metadata_block_picture' in audio_file:
        picture_data = audio_file['metadata_block_picture'][0]
        picture = Picture(b64decode(picture_data))
        return picture.data
    return None


def format_time(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02}:{seconds:02}"


def extract_track_number(track_number):
    """
    Extracts the track number from a string, handling cases like "1/6" or "02/12".
    Returns the integer part before the slash, or the whole number if there's no slash.
    """
    if '/' in track_number:
        return int(track_number.split('/')[0])
    elif track_number.isdigit():
        return int(track_number)
    return float('inf')  # For non-numeric track numbers, place them at the end


def simulate_keypress(widget, key):
    """Simulate keypress for the given widget."""
    key_event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.ControlModifier)
    QCoreApplication.postEvent(widget, key_event)


def getRoundedCornerPixmap(scaled_pixmap, target_width, target_height):
    # Create a transparent pixmap with the same size as the scaled image
    rounded_pixmap = QPixmap(target_width, target_height)
    rounded_pixmap.fill(Qt.GlobalColor.transparent)  # Transparent background

    # Start painting the image with QPainter
    painter = QPainter(rounded_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Create a QPainterPath for the rounded rectangle
    path = QPainterPath()
    radius = 20  # Adjust this for more or less roundness
    path.addRoundedRect(QRectF(0, 0, target_width, target_height), radius, radius)

    # Clip the image to the rounded rectangle
    painter.setClipPath(path)

    # Draw the scaled pixmap into the rounded shape
    painter.drawPixmap(0, 0, scaled_pixmap)
    painter.end()

    return rounded_pixmap


class MusicPlayerUI(QMainWindow):
    def __init__(self, app):
        super().__init__()

        # Define the config path
        self.play_song_at_startup = None
        self.threshold_actions = None
        self.search_bar_layout = None
        self.script_path = os.path.dirname(os.path.abspath(__file__))
        QFontDatabase.addApplicationFont(os.path.join(self.script_path, "fonts/KOMIKAX_.ttf"))

        self.slider_layout = None
        self.duration_label = None
        self.passing_image = None
        self.next_song_button = None
        self.prev_song_button = None
        self.playback_management_layout = None
        self.albumTreeWidget = None
        self.addnewdirectory = AddNewDirectory(self)
        self.color_actions = None
        self.font_settings_window = None
        self.font_settings_action = None
        self.show_lyrics_action = None
        self.tray_menu = None
        self.tray_icon = None
        self.icon_path = None
        self.central_widget = None
        self.songTableWidget = None
        self.search_bar = None
        self.track_display = None
        self.song_details = None
        self.image_display = None
        self.progress_bar = None
        self.slider = None
        self.prev_button = None
        self.click_count = 0
        self.forward_button = None
        self.app = app
        self.file_path = None
        self.hidden_rows = False
        self.play_pause_button = QPushButton()
        self.play_pause_button.setToolTip("Play/Pause")
        self.loop_playlist_button = QPushButton()
        self.loop_playlist_button.setToolTip("Loop Playlist")
        self.repeat_button = QPushButton()
        self.repeat_button.setToolTip("Toggle Repeat")
        self.shuffle_button = QPushButton()
        self.shuffle_button.setToolTip("Toggle Shuffle")
        self.item = None
        self.media_files = []
        self.random_song_list = []
        self.current_playing_random_song_index = None
        self.random_song = None
        self.saved_position = None

        # Screen size
        self.screen_size = self.app.primaryScreen().geometry()

        # Getting image size from primary screen geometry
        self.image_size = int(self.screen_size.width() / 5)  # extract image size from main window

        if platform.system() == "Windows":
            self.config_path = os.path.join(os.getenv('APPDATA'), 'April Music Player')
        else:
            self.config_path = os.path.join(os.path.expanduser("~"), '.config', 'april-music-player')

        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        self.config_file = os.path.join(self.config_path, "configs", "config.json")

        self.ej = EasyJson()
        lrc_font_size = int(self.height() * 0.11)
        if not os.path.exists(self.config_file):
            self.ej.setup_default_values(lrc_font_size=lrc_font_size, fresh_config=True)  # fresh setup default config
        else:
            self.ej.setup_default_values(lrc_font_size=lrc_font_size)

        self.directories = self.ej.get_value("music_directories")

        self.music_file = None
        self.lrc_file = None
        self.music_player = MusicPlayer(self, self.play_pause_button, self.loop_playlist_button, self.repeat_button,
                                        self.shuffle_button, self.play_next_song, self.play_random_song)

        self.lrcPlayer = LRCSync(self, self.music_player, self.config_path, self.on_off_lyrics, self.showMaximized)

    @staticmethod
    def get_metadata(song_file: object):
        if song_file is None:
            return

        file_extension = song_file.lower().split('.')[-1]

        metadata = {
            'title': 'Unknown Title',
            'artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'year': 'Unknown Year',
            'genre': 'Unknown Genre',
            'track_number': 'Unknown Track Number',
            'comment': 'No Comment',
            'duration': 0,  # Initialize duration as integer,
            'file_type': file_extension,
        }

        try:
            if file_extension == "mp3":
                # Extract duration and file_type before crash
                mp3_audio = MP3(song_file)
                metadata['duration'] = int(mp3_audio.info.length)
                metadata['file_type'] = str(file_extension)

                audio = ID3(song_file)
                metadata['title'] = audio.get('TIT2', 'Unknown Title').text[0] if audio.get('TIT2') else 'Unknown Title'
                metadata['artist'] = audio.get('TPE1', 'Unknown Artist').text[0] if audio.get(
                    'TPE1') else 'Unknown Artist'
                metadata['album'] = audio.get('TALB', 'Unknown Album').text[0] if audio.get('TALB') else 'Unknown Album'
                metadata['year'] = audio.get('TDRC', 'Unknown Year').text[0] if audio.get('TDRC') else 'Unknown Year'
                metadata['genre'] = audio.get('TCON', 'Unknown Genre').text[0] if audio.get('TCON') else 'Unknown Genre'
                metadata['track_number'] = audio.get('TRCK', 'Unknown Track Number').text[0] if audio.get(
                    'TRCK') else 'Unknown Track Number'
                metadata['comment'] = audio.get('COMM', 'No Comment').text[0] if audio.get('COMM') else 'No Comment'

            elif file_extension == 'm4a':
                audio = MP4(song_file)

                metadata['title'] = audio.tags.get('\xa9nam', ['Unknown Title'])[0]
                metadata['artist'] = audio.tags.get('\xa9ART', ['Unknown Artist'])[0]
                metadata['album'] = audio.tags.get('\xa9alb', ['Unknown Album'])[0]
                metadata['year'] = audio.tags.get('\xa9day', ['Unknown Year'])[0]
                metadata['genre'] = audio.tags.get('\xa9gen', ['Unknown Genre'])[0]
                metadata['track_number'] = audio.tags.get('trkn', [('Unknown Track Number',)])[0][0]
                metadata['comment'] = audio.tags.get('\xa9cmt', ['No Comment'])[0]

                # Extract duration
                metadata['duration'] = int(audio.info.length)
                metadata['file_type'] = str(file_extension)

            elif file_extension == 'ogg':
                audio = OggVorbis(song_file)
                metadata['title'] = audio.get('title', ['Unknown Title'])[0]
                metadata['artist'] = audio.get('artist', ['Unknown Artist'])[0]
                metadata['album'] = audio.get('album', ['Unknown Album'])[0]
                metadata['year'] = audio.get('date', ['Unknown Year'])[0]
                metadata['genre'] = audio.get('genre', ['Unknown Genre'])[0]
                metadata['track_number'] = audio.get('tracknumber', ['Unknown Track Number'])[0]
                metadata['comment'] = audio.get('comment', ['No Comment'])[0]

                # Extract duration
                metadata['duration'] = int(audio.info.length)
                metadata['file_type'] = str(file_extension)

            elif file_extension == 'flac':
                audio = FLAC(song_file)
                metadata['title'] = audio.get('title', ['Unknown Title'])[0]
                metadata['artist'] = audio.get('artist', ['Unknown Artist'])[0]
                metadata['album'] = audio.get('album', ['Unknown Album'])[0]
                metadata['year'] = audio.get('date', ['Unknown Year'])[0]
                metadata['genre'] = audio.get('genre', ['Unknown Genre'])[0]
                metadata['track_number'] = audio.get('tracknumber', ['Unknown Track Number'])[0]
                metadata['comment'] = audio.get('description', ['No Comment'])[0]

                # Extract duration
                metadata['duration'] = int(audio.info.length)
                metadata['file_type'] = str(file_extension)

            elif file_extension == 'wav':
                audio = WAVE(song_file)
                try:
                    metadata['title'] = audio.get('title', 'Unknown Title')
                    metadata['artist'] = audio.get('artist', 'Unknown Artist')
                    metadata['album'] = audio.get('album', 'Unknown Album')
                    metadata['year'] = audio.get('date', 'Unknown Year')
                    metadata['genre'] = audio.get('genre', 'Unknown Genre')
                    metadata['track_number'] = audio.get('tracknumber', 'Unknown Track Number')
                    metadata['comment'] = audio.get('comment', 'No Comment')
                except KeyError:
                    pass  # WAV files may not contain these tags

                # Extract duration
                metadata['duration'] = int(audio.info.length)
                metadata['file_type'] = str(file_extension)

            else:
                raise ValueError("Unsupported file format")

        except Exception as e:
            print(f"Error reading metadata: {e}")
            print("There might not be metadata tagged in the music file")

        print(f"This is the metadata of {file_extension} file")
        return metadata

    def play_last_played_song(self):
        if self.ej.get_value("play_song_at_startup"):
            pass
        else:
            return

        last_play_file_data = self.ej.get_value("last_played_song")
        if last_play_file_data:
            for file, position in last_play_file_data.items():
                self.music_file = file
                self.saved_position = position

            last_played_items = self.songTableWidget.findItems(self.music_file, Qt.MatchFlag.MatchExactly)
            item = None
            if last_played_items:
                for i in last_played_items:
                    item = i

            print("This is the song from item loaded")
            self.handleRowDoubleClick(item)

        else:
            return

    def toggle_reload_directories(self):
        self.albumTreeWidget.loadSongsToCollection(loadAgain=True)

    def createUI(self):
        self.setWindowTitle("April Music Player - Digest Lyrics")
        self.setGeometry(100, 100, 800, 400)

        # Construct the full path to the icon file
        self.icon_path = os.path.join(self.script_path, 'icons', 'april-icon.png')

        self.setWindowIcon(QIcon(self.icon_path))
        self.createMenuBar()
        self.createWidgetAndLayouts()
        self.showMaximized()
        self.setupTrayIcon()

    def setupTrayIcon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(self.icon_path))
        self.tray_icon.setToolTip("April Music Player")  # Set the tooltip text
        self.tray_icon.setVisible(True)

        self.tray_menu = QMenu()

        open_action = QAction("Open", self)
        open_action.triggered.connect(self.show)
        self.tray_menu.addAction(open_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QCoreApplication.instance().quit)
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_clicked)

    def on_tray_icon_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Handle the left-click (Trigger) event here
            print("Tray icon was left-clicked!")
            if self.isHidden():
                self.show()
            else:
                self.hide()  # Optionally, you can toggle between showing and hiding                

    def closeEvent(self, event):
        print("hiding window")
        self.hide()
        if self.lrcPlayer.lrc_display is not None:
            self.lrcPlayer.lrc_display.close()
        event.ignore()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_I and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            print("disabled lyrics")
            if self.lrcPlayer.show_lyrics:
                self.on_off_lyrics(False)
            else:
                self.on_off_lyrics(True)

        elif event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()

        elif event.key() == Qt.Key.Key_1 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.music_player.thread.isRunning():
                print("Music player's QThread is running.")
            else:
                print("Music player's QThread is not running.")

        elif event.key() == Qt.Key.Key_P and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.stop_song()

        elif event.key() == Qt.Key.Key_Left:
            print("left key pressed")
            self.seekBack()

        elif event.key() == Qt.Key.Key_Right:
            print("right key pressed")
            self.seekForward()

        elif event.key() == Qt.Key.Key_Space:
            print("Space key pressed")
            self.play_pause()

        elif event.key() == Qt.Key.Key_L and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.activate_lrc_display()

        elif event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.exit_app()

        elif event.key() == Qt.Key.Key_F and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.search_bar.setFocus()
            self.search_bar.setCursorPosition(len(self.search_bar.text()))

        elif event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.albumTreeWidget.search_bar.setFocus()
            self.albumTreeWidget.search_bar.setCursorPosition(len(self.search_bar.text()))

        elif event.key() == Qt.Key.Key_R and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            print("playing random song")
            self.play_random_song(user_clicking=True, from_shortcut=True)
            simulate_keypress(self.songTableWidget, Qt.Key.Key_G)

        elif event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.restore_table()

        elif event.key() == Qt.Key.Key_T and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.songTableWidget.setFocus()  # set focus on table

        elif event.key() == Qt.Key.Key_1 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            print("F1 button pressed")
            self.music_player.toggle_loop_playlist()

        elif event.key() == Qt.Key.Key_2 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            print("F2 button pressed")
            self.music_player.toggle_repeat()

        elif event.key() == Qt.Key.Key_3 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            print("F3 button pressed")
            self.music_player.toggle_shuffle()

        else:
            # For other keys, use the default behavior            
            super().keyPressEvent(event)

    def exit_app(self):
        self.songTableWidget.save_table_data()
        self.music_player.save_playback_control_state()
        sys.exit()

    def toggle_add_directories(self):
        self.addnewdirectory.exec()

    def set_default_background_image(self):
        self.ej.setupBackgroundImage()
        self.lrcPlayer.resizeBackgroundImage(self.ej.get_value("background_image"))
        QMessageBox.about(self, "Default Background Image", "Default lyric background image is restored")

    def on_off_lyrics(self, checked):
        if checked:
            self.ej.edit_value("show_lyrics", True)
            self.lrcPlayer.show_lyrics = True
            self.show_lyrics_action.setChecked(True)
            self.lrcPlayer.sync_lyrics(self.lrc_file)

            if not self.lrcPlayer.started_player:
                self.lrcPlayer.media_lyric.setText(self.lrcPlayer.media_font.get_formatted_text("April Music Player"))
                return

            self.lrcPlayer.media_lyric.setText(
                self.lrcPlayer.media_font.get_formatted_text(self.lrcPlayer.lyric_label3_text))

        else:
            print("in disabling")
            self.ej.edit_value("show_lyrics", False)
            self.lrcPlayer.show_lyrics = False
            self.show_lyrics_action.setChecked(False)
            if self.lrcPlayer.media_sync_connected:
                self.music_player.player.positionChanged.disconnect(self.lrcPlayer.update_media_lyric)
                self.lrcPlayer.media_sync_connected = False
            self.lrcPlayer.media_lyric.setText(self.lrcPlayer.media_font.get_formatted_text("Lyrics Disabled"))
            self.lrcPlayer.current_index = 0

    def toggle_on_off_lyrics(self, checked):
        self.on_off_lyrics(checked)

    def show_font_settings(self):
        self.font_settings_window.exec()

    def trigger_play_song_at_startup(self, checked):
        print(checked)
        if checked:
            self.ej.edit_value("play_song_at_startup", True)
        else:
            self.ej.edit_value("play_song_at_startup", False)

    def createMenuBar(self):
        # this is the menubar that will hold all together
        menubar = self.menuBar()

        reload_directories_action = QAction("Reload Music Files", self)
        reload_directories_action.triggered.connect(self.toggle_reload_directories)

        # Actions that will become buttons for each menu
        add_directories_action = QAction("Add Music Directories", self)
        add_directories_action.triggered.connect(self.toggle_add_directories)

        close_action = QAction("Exit", self)
        close_action.triggered.connect(self.exit_app)

        show_shortcuts_action = QAction("Show Shortcuts", self)
        show_shortcuts_action.triggered.connect(self.show_shortcuts)

        preparation_tips = QAction("Preparation of files", self)
        preparation_tips.triggered.connect(self.show_preparation)

        fromMe = QAction("From Developer", self)
        fromMe.triggered.connect(self.show_fromMe)

        add_lrc_background = QAction("Add Lrc Background Image", self)
        add_lrc_background.triggered.connect(self.ask_for_background_image)

        set_default_background = QAction("Set Default Background Image", self)
        set_default_background.triggered.connect(self.set_default_background_image)

        self.show_lyrics_action = QAction("Show Lyrics", self)
        self.show_lyrics_action.setCheckable(True)
        self.show_lyrics_action.setChecked(self.ej.get_value("show_lyrics"))
        self.show_lyrics_action.triggered.connect(self.toggle_on_off_lyrics)

        # Add Font Settings to options menu
        self.font_settings_action = QAction("Font Settings", self)
        self.font_settings_action.triggered.connect(self.show_font_settings)

        self.font_settings_window = FontSettingsWindow(self)

        # Play song at startup action
        self.play_song_at_startup = QAction("Play Song at startup", self)
        self.play_song_at_startup.setCheckable(True)
        self.play_song_at_startup.setChecked(self.ej.get_value("play_song_at_startup"))
        self.play_song_at_startup.triggered.connect(self.trigger_play_song_at_startup)

        # These are main menus in the menu bar
        file_menu = menubar.addMenu("File")
        settings_menu = menubar.addMenu("Settings")
        help_menu = menubar.addMenu("Help")

        settings_menu.addAction(self.play_song_at_startup)
        settings_menu.addAction(self.show_lyrics_action)
        settings_menu.addAction(self.font_settings_action)

        # Add a sub-menu for text color selection with radio buttons
        text_color_menu = QMenu("Choose Lyrics Color", self)
        settings_menu.addMenu(text_color_menu)

        # Create an action group to enforce a single selection (radio button behavior)
        color_group = QActionGroup(self)
        color_group.setExclusive(True)

        # Add color options with radio buttons
        colors = [
            "white", "black", "blue", "yellow", "red", "cyan", "magenta", "orange", "green", "purple",
            "light gray", "dark gray", "turquoise", "brown", "pink", "navy", "teal", "olive", "maroon",
            "lime", "indigo", "violet", "gold", "silver", "beige", "coral", "crimson", "khaki",
            "lavender", "salmon", "sienna", "tan", "plum", "peach", "chocolate"
        ]

        self.color_actions = {}

        for COLOR in colors:
            action = QAction(COLOR, self)
            action.setCheckable(True)

            # Create a colored pixmap for the color sample
            pixmap = QPixmap(20, 20)  # 20x20 is a reasonable size for an icon
            pixmap.fill(QColor(COLOR))  # Fill the pixmap with the color

            # Set the pixmap as the action icon
            icon = QIcon(pixmap)
            action.setIcon(icon)

            self.color_actions[COLOR] = action
            action.setActionGroup(color_group)

            action.triggered.connect(self.get_selected_color)  # Connect to method                        
            text_color_menu.addAction(action)
            self.color_actions[COLOR] = action

        self.color_actions[self.ej.get_value("lyrics_color")].setChecked(True)

        # Add a sub-menu for sync threshold selection with radio buttons
        sync_threshold_menu = QMenu("Choose Syncing Interval", self)
        settings_menu.addMenu(sync_threshold_menu)

        # Add a QLabel at the top of the menu with your message
        label = QLabel(
            "This is basically the refresh rate. Shorter interval provides \nsmoother syncing but uses more CPU.", self)
        label_action = QWidgetAction(self)
        label_action.setDefaultWidget(label)

        # Create an action group to enforce a single selection (radio button behavior)
        threshold_group = QActionGroup(self)
        threshold_group.setExclusive(True)

        # Define threshold options in seconds
        thresholds = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
        self.threshold_actions = {}
        for THRESHOLD in thresholds:
            action = QAction(f"{THRESHOLD} seconds", self)
            action.setCheckable(True)
            action.setActionGroup(threshold_group)
            action.triggered.connect(self.set_sync_threshold)  # Connect to method
            sync_threshold_menu.addAction(action)
            self.threshold_actions[THRESHOLD] = action

        sync_threshold_menu.addAction(label_action)

        # Set the previously selected threshold
        self.threshold_actions[self.ej.get_value("sync_threshold")].setChecked(True)

        # Linking actions and menus
        file_menu.addAction(reload_directories_action)
        file_menu.addAction(add_directories_action)
        file_menu.addAction(close_action)
        help_menu.addAction(fromMe)
        help_menu.addAction(preparation_tips)
        help_menu.addAction(show_shortcuts_action)
        settings_menu.addAction(add_lrc_background)
        settings_menu.addAction(set_default_background)

    def get_selected_color(self):
        selected_color = self.ej.get_value("lyrics_color")
        for color, action in self.color_actions.items():
            if action.isChecked():
                selected_color = color
                break
        print(f"Selected color: {selected_color}")
        self.ej.edit_value("lyrics_color", selected_color.lower())

    # Method to update sync threshold
    def set_sync_threshold(self):
        selected_threshold = self.ej.get_value("sync_threshold")
        for threshold, action in self.threshold_actions.items():
            if action.isChecked():
                selected_threshold = threshold
                break
        print(f"Selected Threshold: {selected_threshold}")
        self.ej.edit_value("sync_threshold", selected_threshold)
        self.lrcPlayer.update_interval = selected_threshold

    def show_fromMe(self):
        text = """<b>This project was developed to "the version 1 released" solely by me. I wish I could get 
        collaborations that I could code together. I would greatly appreciate any contributions to this project. If 
        you found April useful, I'd appreciate it if you could give the project a star on GitHub!</b> <a 
        href="https://github.com/amm926616/April-Music-Player">Project's GitHub link</a><br><br>

        <b>Created with love by AD178.</b><br>
        <b>Contact me on Telegram: </b><a href="https://t.me/Adamd178">Go to Adam's Telegram</a><br>
        """
        QMessageBox.information(self, "Thank you for using April", text)

    def show_preparation(self):
        text = """<b>Before using the player, you'll need to download your songs and lyrics in advance. I use Zotify 
        to download songs from Spotify, and for LRC lyrics files, I recommend using LRCGET, Syrics on your laptop, 
        or SongSync on Android. There are also various websites where you can download music with embedded metadata 
        and lyrics.</b><br> - <a href="https://github.com/zotify-dev/zotify">Zotify</a><br> - <a 
        href="https://github.com/tranxuanthang/lrcget">LRCGET</a><br> - <a 
        href="https://github.com/akashrchandran/syrics">Syrics</a><br> - <a 
        href="https://github.com/Lambada10/SongSync">SongSync</a><br><br> <b>For the program to easily match and grab 
        files, ensure that the music file and the LRC file have the same name, plus in the same directory. I will 
        figure out for better file management in the future.</b>"""
        QMessageBox.information(self, "Preparation of files", text)

    def show_shortcuts(self):
        shortcuts_text = """         
        <b>Keyboard Shortcuts</b><br><br>
        
        <b>General:</b> <ul> <li><strong>Left Arrow, Right Arrow, Spacebar</strong>: Seek backward, seek forward, 
        and play/pause, respectively.</li> <li><strong>Ctrl + L</strong>: Activate LRC display, or double-click the 
        progress bar.</li> <li><strong>Ctrl + S</strong>: Focus and place cursor on search bar. Empty Search reloads 
        default table.</li> <li><strong>Ctrl + Q</strong>: This shortcut quits the program. The program runs in the 
        background even if you close the main window.</li> <li><strong>Ctrl + I</strong>: Activate/Disable 
        Lyrics.</li> <li><strong>Ctrl + G</strong>: Go to current playing music.</li> </ul> <b>In LRC view</b>: <ul> 
        <li><strong>F</strong>: Toggle full-screen mode.</li> <li><strong>D</strong>: Go to the start of current 
        lyric.</li> <li><strong>Up Arrow, Down Arrow</strong>: Seek to the previous or next lyric line.</li> 
        <li><strong>E</strong>: To activate Note Book</li> </ul> <b>In Lyrics Notebook</b>: <ul> <li><strong>Ctrl + 
        S</strong>: To save written text.</li> <li><strong>Esc</strong>, <strong>Ctrl + W</strong>, <strong>Alt + 
        F4</strong>: To exit without saving.</li> </ul>"""
        QMessageBox.information(self, "Shortcuts", shortcuts_text)

    def ask_for_background_image(self):
        # Open a file dialog and get the selected file
        file_path, _ = QFileDialog.getOpenFileName(self, "Select an Image file for lrc display background image")

        if file_path:
            self.ej.edit_value("background_image", file_path)
            self.lrcPlayer.resizeBackgroundImage(self.ej.get_value("background_image"))
            # Show the selected file path in a QMessageBox
            QMessageBox.information(self, "Load Background Image", f"You selected: {file_path}")
        else:
            QMessageBox.warning(self, "No File Selected", "You did not select any file.")

    def show_context_menu(self, pos):
        # Get the item at the clicked position
        item = self.songTableWidget.itemAt(pos)

        if item and "Album Title:" not in item.text():
            # Create the context menu
            context_menu = QMenu(self)

            # Add an action to copy the file path
            copy_action = context_menu.addAction("Copy Song Path")

            # Connect the action to a method
            copy_action.triggered.connect(lambda: self.copy_item_path(item))

            file_tagger_action = context_menu.addAction("Edit Song's Metadata")
            file_tagger_action.triggered.connect(self.activate_file_tagger)

            # Show the context menu at the cursor position
            context_menu.exec(QCursor.pos())

    def copy_item_path(self, item):
        file = self.get_music_file_from_click(item)
        if file:
            self.app.clipboard().setText(file)
        else:
            pass

    def activate_file_tagger(self):
        currentRow = self.songTableWidget.currentRow()
        music_file = self.songTableWidget.item(currentRow, 7).text()
        tagger = TagDialog(self, music_file, self.songTableWidget, self.albumTreeWidget, self.albumTreeWidget.cursor,
                           self.albumTreeWidget.conn)
        tagger.exec()

    def createWidgetAndLayouts(self):
        """ The main layout of the music player ui"""
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        main_layout = QHBoxLayout()
        self.central_widget.setLayout(main_layout)

        # Initialize the table widget
        self.songTableWidget = SongTableWidget(self, self.handleRowDoubleClick, self.music_player.seek_forward,
                                               self.music_player.seek_backward, self.play_pause, self.config_path,
                                               self.screen_size.height())

        self.songTableWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.songTableWidget.customContextMenuRequested.connect(self.show_context_menu)
        self.songTableWidget.setColumnCount(9)  # 7 for metadata + 1 for file path
        self.songTableWidget.setHorizontalHeaderLabels(
            ['Title', 'Artist', 'Album', 'Year', 'Genre', 'Track Number', 'Duration', 'File Path', "Media Type"]
        )

        # Set selection behavior to select entire rows
        self.songTableWidget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.songTableWidget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Connect the itemClicked signal to the custom slot
        self.songTableWidget.itemDoubleClicked.connect(self.handleRowDoubleClick)

        # Adjust column resizing
        header = self.songTableWidget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)  # Stretch all columns

        # Creating the 3 main layouts

        song_collection_layout = QVBoxLayout()
        self.albumTreeWidget = AlbumTreeWidget(self, self.songTableWidget)
        self.albumTreeWidget.loadSongsToCollection(self.directories)
        song_collection_layout.addWidget(self.albumTreeWidget)

        playlistLayout = QVBoxLayout()
        playlistLayout.addWidget(self.songTableWidget)

        mediaLayout = QVBoxLayout()

        main_layout.addLayout(song_collection_layout, 3)
        main_layout.addLayout(playlistLayout, 13)
        main_layout.addLayout(mediaLayout, 4)

        self.setupSongListWidget(playlistLayout)
        self.setupMediaPlayerWidget(mediaLayout)

    def setupSongListWidget(self, left_layout):
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.setFocus()  # Place the cursor in the search bar

        # Connect search bar returnPressed signal to the search method
        self.search_bar.returnPressed.connect(self.filterSongs)

        self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "loop-playlist.ico")))
        self.loop_playlist_button.clicked.connect(self.music_player.toggle_loop_playlist)

        self.repeat_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "repeat.ico")))
        self.repeat_button.clicked.connect(self.music_player.toggle_repeat)

        self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "shuffle.ico")))
        self.shuffle_button.clicked.connect(self.music_player.toggle_shuffle)

        self.playback_management_layout = QHBoxLayout()
        self.playback_management_layout.addWidget(self.loop_playlist_button)
        self.playback_management_layout.addWidget(self.repeat_button)
        self.playback_management_layout.addWidget(self.shuffle_button)

        self.search_bar_layout = QHBoxLayout()
        self.search_bar_layout.addLayout(self.playback_management_layout)
        self.search_bar_layout.addWidget(self.search_bar)

        left_layout.addLayout(self.search_bar_layout)
        if self.ej.get_value("music_directories") is None:
            self.addnewdirectory.add_directory()

        self.music_player.setup_playback_control_state()

    def setupMediaPlayerWidget(self, right_layout):
        # Create a widget to hold the media player components
        media_widget = QWidget()

        # Create and configure the layout for the media widget
        mediaLayout = QVBoxLayout(media_widget)

        # Create and configure the track display label
        self.track_display = QLabel("No Track Playing")
        self.track_display.setFont(QFont("Komika Axis"))
        self.track_display.setWordWrap(True)
        self.track_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.track_display.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.track_display.setStyleSheet("font-size: 20px")

        # Create and configure the image display label
        self.image_display = ClickableLabel()
        self.image_display.doubleClicked.connect(self.double_click_on_image)

        # Create and configure the song details label
        self.song_details = QLabel()
        self.song_details.setWordWrap(True)  # Ensure the text wraps within the label

        # Create a QWidget to hold the layout
        container_widget = QWidget()

        # Create a QVBoxLayout and add self.song_details to it
        layout = QVBoxLayout(container_widget)
        layout.addWidget(self.song_details)
        layout.addStretch()  # This will push self.song_details to the top

        # Set the layout as the widget of the scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(container_widget)

        # Add widgets to the vertical layout
        mediaLayout.addWidget(self.track_display)
        mediaLayout.addWidget(self.image_display)
        mediaLayout.addWidget(scroll_area)  # Add the scroll area instead of the label directly
        mediaLayout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Add the media_widget to the right_layout
        right_layout.addWidget(media_widget)

        # Set up the media player controls panel
        self.setupMediaPlayerControlsPanel(right_layout)

    def slider_key_event(self, event):
        # to catch key event on slider.
        if event.key() == Qt.Key.Key_Left:
            print("left key pressed")
            self.seekBack()

        elif event.key() == Qt.Key.Key_Right:
            print("right key pressed")
            self.seekForward()

        elif event.key() == Qt.Key.Key_Space:
            print("Space key pressed")
            self.play_pause()

    def update_slider(self, position):
        self.update_progress_label(self.music_player.player.position())
        self.slider.setValue(position)

    def update_slider_range(self, duration):
        self.slider.setRange(0, duration)

    def activate_lrc_display(self):
        self.hide()
        if self.lrcPlayer.lrc_display is not None:
            pass
        else:
            self.lrcPlayer.startUI(self, self.lrc_file)

    def update_progress_label(self, position):
        # Calculate current time and total time
        current_time = format_time(position // 1000)  # Convert from ms to seconds
        total_time = format_time(self.music_player.get_duration() // 1000)  # Total duration in seconds

        duration_string = f"[{current_time}/{total_time}]"
        self.duration_label.setText(duration_string)

    def setupMediaPlayerControlsPanel(self, right_layout):
        self.slider_layout = QHBoxLayout()

        self.duration_label = QLabel()

        # Create a QSlider
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider_layout.addWidget(self.slider)
        self.slider_layout.addWidget(self.duration_label)
        self.slider.keyPressEvent = self.slider_key_event
        self.slider.setRange(0, self.music_player.get_duration())
        self.slider.setValue(0)

        # Connect the slider to the player's position
        self.music_player.player.positionChanged.connect(self.update_slider)
        self.music_player.player.durationChanged.connect(self.update_slider_range)
        self.slider.sliderMoved.connect(self.update_player_from_slider)

        self.lrcPlayer.media_lyric.doubleClicked.connect(self.activate_lrc_display)
        right_layout.addWidget(self.lrcPlayer.media_lyric)
        self.lrcPlayer.media_lyric.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        right_layout.addLayout(self.slider_layout)

        controls_layout = QHBoxLayout()
        self.prev_button = QPushButton()
        self.prev_button.setToolTip("seek backward(-1s)")
        self.forward_button = QPushButton()
        self.forward_button.setToolTip("seek forward(+1s)")
        self.prev_song_button = QPushButton()
        self.prev_song_button.setToolTip("Previous Song")
        self.next_song_button = QPushButton()
        self.next_song_button.setToolTip("Next Song")

        # Set size policy for the buttons to ensure consistent height
        # Set size policy for the buttons to ensure consistent height
        size_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.prev_button.setSizePolicy(size_policy)
        self.forward_button.setSizePolicy(size_policy)
        self.play_pause_button.setSizePolicy(size_policy)
        self.prev_song_button.setSizePolicy(size_policy)
        self.next_song_button.setSizePolicy(size_policy)

        self.prev_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "seek-backward.ico")))
        self.play_pause_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "play.ico")))
        self.forward_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "seek-forward.ico")))
        self.prev_song_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "previous-song.ico")))
        self.next_song_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "next-song.ico")))

        self.prev_button.clicked.connect(self.seekBack)
        self.play_pause_button.clicked.connect(self.play_pause)
        self.forward_button.clicked.connect(self.seekForward)
        self.prev_song_button.clicked.connect(self.play_previous_song)
        self.next_song_button.clicked.connect(self.play_next_song)

        controls_layout.addWidget(self.prev_song_button)
        controls_layout.addWidget(self.prev_button)
        controls_layout.addWidget(self.play_pause_button)
        controls_layout.addWidget(self.forward_button)
        controls_layout.addWidget(self.next_song_button)

        right_layout.addLayout(controls_layout)
        self.play_last_played_song()

    def updateDisplayData(self):
        metadata = self.get_metadata(self.music_file)
        updated_text = f'{metadata["artist"]} - {metadata["title"]}'
        self.track_display.setText(updated_text)

    def updateSongDetails(self, song_file):
        metadata = self.get_metadata(song_file)
        minutes = metadata["duration"] // 60
        seconds = metadata["duration"] % 60
        # Define the bold HTML tag
        BOLD = '<b>'
        END = '</b>'

        updated_text = (
            f'<div>{BOLD}[Track Details]{END}</div>'
            f'<div>{BOLD}Title{END}: {metadata["title"]}</div>'
            f'<div>{BOLD}Artist{END}: {metadata["artist"]}</div>'
            f'<div>{BOLD}Album{END}: {metadata["album"]}</div>'
            f'<div>{BOLD}Release Date{END}: {metadata["year"]}</div>'
            f'<div>{BOLD}Genre{END}: {metadata["genre"]}</div>'
            f'<div>{BOLD}Track Number{END}: {metadata["track_number"]}</div>'
            f'<div>{BOLD}Comment{END}: {metadata["comment"]}</div>'
            f'<div>{BOLD}Duration{END}: {minutes}:{seconds:02d}</div>'
            f'<div>{BOLD}File Path{END}: {song_file}</div>'
        )

        self.song_details.setText(updated_text)
        # Set text interaction to allow text selection
        self.song_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.song_details.setWordWrap(True)

    def restore_table(self):
        for row in range(self.songTableWidget.rowCount()):
            self.songTableWidget.setRowHidden(row, False)

    def filterSongs(self):
        self.hidden_rows = True
        self.songTableWidget.clearSelection()  # Clear previous selections (highlighting)    
        if self.search_bar.hasFocus():
            search_text = self.search_bar.text().lower()

            if search_text == "":  # If the search text is empty, reset the table view
                self.restore_table()

            elif search_text == "random":  # If the search text is "random", play a random song
                self.play_random_song()

            elif search_text == "crash":
                raise RuntimeError("Purposely crashing the app with an uncaught exception")

            else:
                found_at_least_one = False  # Flag to track if at least one match is found
                for row in range(self.songTableWidget.rowCount()):
                    match = False
                    item = self.songTableWidget.item(row, 0)  # Check the first column of each row

                    # Hide album title rows (rows containing 'Album Title:')
                    if item and "Album Title:" in item.text():
                        self.songTableWidget.setRowHidden(row, True)
                        continue  # Skip further processing for album title rows

                    # Now filter regular song rows
                    for column in range(2):  # Check first two columns for a match
                        item = self.songTableWidget.item(row, column)
                        if item and search_text in item.text().lower():
                            match = True
                            found_at_least_one = True  # Set flag to True if at least one match is found
                            break

                    # Highlight matched rows and hide unmatched rows if at least one match is found
                    if found_at_least_one:
                        self.songTableWidget.setRowHidden(row, not match)
                        # if match:
                        #     self.songTableWidget.selectRow(row)  # Highlight the row if it matches                        
                        #     self.songTableWidget.scroll_to_current_row()                                                    
                    else:
                        self.songTableWidget.setRowHidden(row, True)  # Hide the other rows

            # Clear the search bar and reset the placeholder text
            self.search_bar.clear()
            self.search_bar.setPlaceholderText("Search...")

    def cleanDetails(self):
        # clear the remaining from previous play
        self.lrcPlayer.file = None
        self.music_player.player.stop()
        self.track_display.setText("No Track Playing")
        self.image_display.clear()
        self.song_details.clear()

    def update_information(self):
        if self.music_file:
            self.updateDisplayData()
            self.extract_and_set_album_art()
            self.updateSongDetails(self.music_file)
        else:
            return

    def get_music_file_from_click(self, item):
        if "Album Title:" in item.text():
            return

        row = item.row()
        self.file_path = self.songTableWidget.item(row, 7).text()  # Retrieve the file path from the hidden column

        if not os.path.isfile(self.file_path):
            # File does not exist
            QMessageBox.warning(self, 'File Not Found', f'The file at {self.file_path} does not exist.')
            self.file_path = None
            self.music_file = None
        else:
            self.music_file = self.file_path

        return self.file_path

    def find_row(self, target_file_path):
        # Loop through each row in the table
        for row in range(self.songTableWidget.rowCount()):
            item = self.songTableWidget.item(row, 7)
            if item:
                current_file_path = self.songTableWidget.item(row, 7).text()

                # Check if the current file path matches the target file path
                if current_file_path == target_file_path:
                    print(f"File found in row: {row}")
                    # Perform any action you want with the found row, such as selecting it
                    self.songTableWidget.selectRow(row)
                    return row
        else:
            print("File path not found.")

    def song_initializing_stuff(self):
        self.update_information()
        self.get_lrc_file()
        self.music_player.update_music_file(self.music_file)
        self.music_player.default_pause_state()
        self.play_song()

    def get_random_song_list(self):
        # Create a list excluding the current song (self.music_file)

        print("inside get random song list method")

        random_song_list = self.songTableWidget.files_on_playlist.copy()
        shuffle(random_song_list)

        print("After shuffling, the random song list items")
        print(random_song_list)

        return random_song_list

    def prepare_for_random(self):
        self.random_song_list.clear()
        self.random_song_list = self.get_random_song_list()
        # Remove the current music file if it's in the list, Making current playing file as first index
        if self.music_file in self.random_song_list:
            self.random_song_list.remove(self.music_file)

            # Insert the music file at the beginning of the list
            self.random_song_list.insert(0, self.music_file)

        self.current_playing_random_song_index = 0

    def play_previous_song(self):
        if self.music_player.music_on_shuffle:
            self.current_playing_random_song_index -= 1
            if self.current_playing_random_song_index < 1:
                self.current_playing_random_song_index = len(self.random_song_list) - 1
            self.play_random_song(user_clicking=True)
        else:
            previous_song = self.songTableWidget.get_previous_song_object()
            self.handleRowDoubleClick(previous_song)

    def play_next_song(self, fromStart=None):
        if fromStart:
            next_song = self.songTableWidget.get_next_song_object(fromstart=True)
            self.handleRowDoubleClick(next_song)
            return

        if self.music_player.music_on_shuffle:
            self.current_playing_random_song_index += 1
            if self.current_playing_random_song_index > len(self.random_song_list) - 1:
                self.current_playing_random_song_index = 0
            self.play_random_song(user_clicking=True)
        else:
            next_song = self.songTableWidget.get_next_song_object(fromstart=False)
            self.handleRowDoubleClick(next_song)

    def play_random_song(self, user_clicking=False, from_shortcut=False):
        if not self.songTableWidget.files_on_playlist:
            return
        self.songTableWidget.clearSelection()

        print(self.current_playing_random_song_index, "current index")

        if not user_clicking:  # without user clicking next/previous
            print("max len is ", len(self.random_song_list))

            self.current_playing_random_song_index += 1

            if self.current_playing_random_song_index > len(self.random_song_list) - 1:
                self.lrcPlayer.media_lyric.setText(
                    self.lrcPlayer.media_font.get_formatted_text(self.music_player.eop_text))
                return

        if from_shortcut:
            self.music_file = choice(self.songTableWidget.files_on_playlist)
        else:
            self.music_file = self.random_song_list[self.current_playing_random_song_index]

        random_song_row = self.find_row(self.music_file)
        self.songTableWidget.song_playing_row = random_song_row

        # Here is to start doing the normal stuff of preparation and playing song.        
        self.song_initializing_stuff()

    def handleRowDoubleClick(self, item):
        row = None
        try:
            row = item.row()
        except AttributeError:
            return

        if item:
            if "Album Title: " in item.text():
                return
            else:
                self.item = item
                self.songTableWidget.song_playing_row = row
                self.lrcPlayer.started_player = True
                self.get_music_file_from_click(item)
                if self.music_file:
                    self.song_initializing_stuff()
                else:
                    return
        else:
            return

        if self.hidden_rows:
            self.songTableWidget.clearSelection()
            self.restore_table()
            self.songTableWidget.setFocus()
            self.songTableWidget.scroll_to_current_row()
            simulate_keypress(self.songTableWidget, Qt.Key.Key_G)  # only imitation of key press work.
            # Direct calling the method doesn't work. IDk why.
            self.hidden_rows = False

    def stop_song(self):
        if self.music_player.started_playing:
            self.music_player.player.stop()
            self.lrcPlayer.started_player = False
            self.lrcPlayer.disconnect_syncing()
            self.play_pause_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "play.ico")))
            self.lrcPlayer.media_lyric.setText(self.lrcPlayer.media_font.get_formatted_text("April Music Player"))
            self.music_player.started_playing = False

    def play_song(self):
        # current for checking lrc on/off state and then play song
        self.play_pause_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "pause.ico")))
        if self.lrcPlayer.show_lyrics:
            self.lrcPlayer.sync_lyrics(self.lrc_file)
        else:
            if self.lrcPlayer.media_sync_connected:
                self.music_player.player.positionChanged.disconnect(self.lrcPlayer.update_media_lyric)
                self.lrcPlayer.media_sync_connected = False

        self.music_player.started_playing = True
        self.music_player.play()

        if self.saved_position:
            self.music_player.player.setPosition(int(self.saved_position))
        else:
            self.music_player.player.setPosition(int(0))

    def seekBack(self):
        self.music_player.seek_backward()

    def seekForward(self):
        self.music_player.seek_forward()

    def play_pause(self):
        # for checking eop then calling button changing method for play/pause
        current_text = html_to_plain_text(self.lrcPlayer.media_lyric.text())
        if current_text == self.music_player.eop_text:
            if self.music_player.music_on_shuffle:
                self.random_song_list = self.get_random_song_list()
                self.current_playing_random_song_index = 0
                self.play_random_song(user_clicking=True)
            else:
                self.play_next_song(True)
        else:
            self.music_player.play_pause_music()

    def update_player_from_slider(self, position):
        # Set the media player position when the slider is moved
        self.music_player.player.setPosition(position)

    def get_lrc_file(self):
        if self.music_file.endswith(".ogg"):
            lrc = self.music_file.replace(".ogg", ".lrc")
        elif self.music_file.endswith(".mp3"):
            lrc = self.music_file.replace(".mp3", ".lrc")
        else:
            lrc = None

        if lrc and os.path.exists(lrc):
            self.lrc_file = lrc
        else:
            self.lrc_file = None
            self.lrcPlayer.file = None
            self.lrcPlayer.music_file = self.music_file

    def double_click_on_image(self):
        if self.music_file is None:
            return
        elif self.image_display.text() == "No Album Art Found":
            return
        else:
            album_window = AlbumImageWindow(self, self.passing_image, self.icon_path, self.music_file,
                                            self.screen_size.height())
            album_window.exec()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def extract_and_set_album_art(self):
        audio_file = File(self.music_file)

        if isinstance(audio_file, MP3):
            album_image_data = extract_mp3_album_art(audio_file)
        elif isinstance(audio_file, OggVorbis):
            album_image_data = extract_ogg_album_art(audio_file)
        elif isinstance(audio_file, FLAC):
            album_image_data = extract_flac_album_art(audio_file)
        elif isinstance(audio_file, MP4) or audio_file.mime[0] == 'video/mp4':  # Handle both MP4 and M4A
            album_image_data = extract_mp4_album_art(audio_file)
        elif audio_file.mime[0] == 'audio/x-wav':
            try:
                id3_tags = ID3(self.music_file)
                apic = id3_tags.getall('APIC')  # APIC frames contain album art in ID3
                album_image_data = apic[0].data if apic else None
            except ID3NoHeaderError:
                album_image_data = None  # Handle cases where there's no ID3 tag or image
        else:
            album_image_data = None

        if album_image_data:
            pixmap = QPixmap()
            pixmap.loadFromData(album_image_data)
        else:
            # Load a default image if no album art is found
            pixmap = QPixmap(os.path.join(self.script_path, "icons/april-logo.png"))

        self.passing_image = pixmap  # for album art double-clicking

        # Continue with the process of resizing, rounding, and setting the pixmap
        scaled_pixmap = pixmap.scaled(self.image_size, self.image_size,
                                      aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
                                      transformMode=Qt.TransformationMode.SmoothTransformation)

        rounded_pixmap = getRoundedCornerPixmap(scaled_pixmap, self.image_size, self.image_size)

        # Set the final rounded image to QLabel
        self.image_display.setPixmap(rounded_pixmap)
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignHCenter)
