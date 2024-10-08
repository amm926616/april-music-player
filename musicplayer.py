from PyQt6.QtGui import QIcon
import os
from PyQt6.QtCore import QThread, QObject, pyqtSignal
from easy_json import EasyJson
from musicplayerworker import MusicPlayerWorker


class MusicPlayer:
    def __init__(self, parent, play_pause_button, loop_playlist_button, repeat_button, shuffle_button,
                 playNextSong=None, playRandomSong=None):
        self.parent = parent
        self.ej = EasyJson()
        self.playNextSong = playNextSong
        self.playRandomSong = playRandomSong
        self.file_name = None
        self.eop_text = "End Of Playlist"
        self.player = MusicPlayerWorker(self.handle_media_status_changed)  # Create a worker instance

        self.thread = QThread()  # Create a QThread

        # Move the worker to the thread
        self.player.moveToThread(self.thread)

        # Connect signals and slots
        self.thread.started.connect(self.player.play)  # When the thread starts, the worker will play the song
        self.thread.finished.connect(self.thread.deleteLater)  # Clean up when the thread is finished

        self.started_playing = False
        self.in_pause_state = False
        self.music_on_repeat = None
        self.music_on_shuffle = None
        self.playlist_on_loop = None
        self.previous_shuffle_state = None
        self.previous_loop_state = None
        self.paused_position = 0.0

        self.play_pause_button = play_pause_button
        self.loop_playlist_button = loop_playlist_button
        self.repeat_button = repeat_button
        self.shuffle_button = shuffle_button
        self.script_path = os.path.dirname(os.path.abspath(__file__))

    def play(self):
        self.started_playing = True
        self.update_music_file(self.file_name)
        self.thread.start()  # Start the thread to play the song in the background
        self.player.play()

    def save_playback_control_state(self):
        self.ej.edit_value("previous_loop", self.previous_loop_state)
        self.ej.edit_value("previous_shuffle", self.previous_shuffle_state)
        self.ej.edit_value("shuffle", self.music_on_shuffle)
        self.ej.edit_value("loop", self.playlist_on_loop)
        self.ej.edit_value("repeat", self.music_on_repeat)

    def setup_playback_control_state(self):
        self.previous_loop_state = self.ej.get_value("previous_loop")
        self.previous_shuffle_state = self.ej.get_value("previous__shuffle")
        self.music_on_repeat = self.ej.get_value("repeat")
        self.music_on_shuffle = self.ej.get_value("shuffle")
        self.playlist_on_loop = self.ej.get_value("loop")

        if self.music_on_repeat:
            self.repeat_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "on-repeat.ico")))
            self.repeat_button.setToolTip("On Repeat")
            self.disable_shuffle(no_setup=False)
            self.disable_loop_playlist(no_setup=False)

        elif self.music_on_shuffle:
            self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "on-shuffle.ico")))
            self.shuffle_button.setToolTip("On Shuffle")
            self.parent.prepare_for_random()
            self.disable_loop_playlist(no_setup=False)

        elif self.playlist_on_loop:
            self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons",
                                                                 "on-loop-playlist.ico")))
            self.loop_playlist_button.setToolTip("On Playlist Looping")

    def toggle_loop_playlist(self):
        if self.playlist_on_loop:
            self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons",
                                                                 "loop-playlist.ico")))
            self.loop_playlist_button.setToolTip("Toggle Playlist Looping")
            self.playlist_on_loop = False
        else:
            self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons",
                                                                 "on-loop-playlist.ico")))
            self.loop_playlist_button.setToolTip("On Playlist Looping")
            self.playlist_on_loop = True

    def toggle_repeat(self):
        if self.music_on_repeat:
            self.repeat_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "repeat.ico")))
            self.repeat_button.setToolTip("Toggle Repeat")
            self.music_on_repeat = False
        else:
            self.repeat_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "on-repeat.ico")))
            self.repeat_button.setToolTip("On Repeat")
            self.music_on_repeat = True

        self.disable_shuffle()
        self.disable_loop_playlist()

    def toggle_shuffle(self):
        if self.music_on_shuffle:
            self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "shuffle.ico")))
            self.shuffle_button.setToolTip("Toggle Shuffle")
            self.music_on_shuffle = False
        else:
            self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "on-shuffle.ico")))
            self.shuffle_button.setToolTip("On Shuffle")
            self.music_on_shuffle = True
            self.parent.prepare_for_random()

        self.disable_loop_playlist()

    def disable_loop_playlist(self, no_setup=True):
        if self.music_on_repeat or self.music_on_shuffle:
            self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons",
                                                                 "loop-playlist-off.ico")))
            self.loop_playlist_button.setDisabled(True)
            self.previous_loop_state = self.playlist_on_loop
            self.playlist_on_loop = False
        else:
            if no_setup:
                self.loop_playlist_button.setDisabled(False)
                self.playlist_on_loop = self.previous_loop_state
                if self.playlist_on_loop:
                    self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons",
                                                                         "on-loop-playlist.ico")))
                else:
                    self.loop_playlist_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons",
                                                                         "loop-playlist.ico")))

    def disable_shuffle(self, no_setup=True):
        if self.music_on_repeat:
            self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "shuffle-off.ico")))
            self.shuffle_button.setDisabled(True)
            self.previous_shuffle_state = self.music_on_shuffle
            self.music_on_shuffle = False
        else:
            if no_setup:
                self.shuffle_button.setDisabled(False)
                self.music_on_shuffle = self.previous_shuffle_state
                if self.music_on_shuffle:
                    self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "on-shuffle.ico")))
                else:
                    self.shuffle_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "shuffle.ico")))

    def default_pause_state(self):
        self.in_pause_state = False
        self.paused_position = 0.0

    def update_music_file(self, file):
        self.file_name = file
        self.player.setSource(self.file_name)

    def play_pause_music(self):
        if self.started_playing:  # pause state activating
            if not self.in_pause_state:
                # Record the current position before pausing
                self.paused_position = self.player.position()  # Assuming get_position() returns
                # the current position in seconds or milliseconds

                self.player.pause()
                self.in_pause_state = True
                self.play_pause_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "play.ico")))
            else:
                # Set the position to the recorded value before resuming
                self.player.setPosition(self.paused_position)  # Assuming set_position() sets the playback position

                # Continue playing
                self.player.play()
                self.in_pause_state = False
                self.play_pause_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "pause.ico")))

    def pause(self):
        self.paused_position = self.player.position()  # Assuming get_position()
        # returns the current position in seconds or milliseconds
        self.in_pause_state = True
        self.play_pause_button.setIcon(QIcon(os.path.join(self.script_path, "media-icons", "play.ico")))
        self.player.pause()

    def get_current_time(self):
        position = self.player.position() / 1000.0
        return position

    def seek_forward(self, saved_position=None):
        if self.player.isPlaying and not saved_position:
            self.player.setPosition(self.player.position() + 1000)
        else:
            self.player.setPosition(saved_position)

    def seek_backward(self):
        if self.player.isPlaying:
            self.player.setPosition(self.player.position() - 1000)

    def get_duration(self):
        return self.player.duration()

    def get_position(self):
        return self.player.position()

    def handle_media_status_changed(self, status):
        if status == self.player.MediaStatus.EndOfMedia:
            if self.music_on_repeat:
                # Restart playback
                self.player.setPosition(0)
                self.player.play()
            else:
                if self.music_on_shuffle:
                    self.playRandomSong()
                else:
                    self.playNextSong()
