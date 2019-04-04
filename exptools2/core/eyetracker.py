import pylink
import os.path as op
import numpy as np
from datetime import datetime
from psychopy import core
from psychopy import misc
from psychopy import event
from psychopy.iohub import launchHubServer
from psychopy.sound import Sound
from psychopy.visual import TextStim, Circle

from .session import Session
from .trial import Trial


class PylinkEyetrackerSession(Session):

    def __init__(self, output_str, eyetracker_on=True, **kwargs):
        """ Initializes EyetrackerSession class.
        
        parameters
        ----------
        output_str : str
            Name (string) for output-files (e.g., 'sub-01_ses-post_run-1')
        eyetracker_on : bool
            Whether the eyetracker is actually on
        kwargs : dict
            Extra arguments to base Session class initialization

        attributes
        ----------
        tracker : Eyelink
            Pylink 'Eyelink' object
        display : PsychopyCustomDisplay
            exptools2' PsychopyCustomDisplay object
        """
        super().__init__(output_str, **kwargs)
        self.eyetracker_on = eyetracker_on
        self.et_settings = self.settings['eyetracker']  # for convenience
        self.tracker = self._create_tracker()
        self.display = self._create_display()
        self._set_options_tracker()

    def _create_tracker(self):
        """ Creates tracker object upon initialization. """
        if not self.eyetracker_on:
            return None

        tracker = pylink.EyeLink(trackeraddress=self.et_settings.get('address'))
        pylink.flushGetkeyQueue()
        tracker.setOfflineMode()

        self.edf_name = datetime.now().strftime('%H_%M_%S.edf')
        tracker.openDataFile(self.edf_name)
        return tracker

    def _set_options_tracker(self):
        """ Sets a bunch of options . """
        # Set content of edf file (@Tomas: what are sensible defaults?)
        cmds = [
            'file_event_filter = LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT',
            'link_event_filter = LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON',
            'link_sample_data = LEFT,RIGHT,GAZE,GAZERES,AREA,STATUS,HTARGET',
            'file_sample_data = LEFT,RIGHT,GAZE,AREA,GAZERES,STATUS,HTARGET,INPUT',
            f"sample_rate = {self.et_settings['sample_rate']}",
            'set_idle_mode',
        ]

        #self.sendCommand("file_event_filter = LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON")
		#self.sendCommand("file_sample_data  = LEFT,RIGHT,GAZE,AREA,GAZERES,STATUS,HREF,PUPIL")
		#self.sendCommand("link_event_filter = LEFT,RIGHT,FIXATION,FIXUPDATE,SACCADE,BLINK,BUTTON")
		#self.sendCommand("link_sample_data  = LEFT,RIGHT,GAZE,GAZERES,AREA,STATUS")

        for cmd in cmds:
            self.tracker.sendCommand(cmd)
            core.wait(0.05)  # give the tracker some leeway
		
        self.tracker.setCalibrationType(self.et_settings.get('calib_type'))
        self.tracker.setAutoCalibrationPacing(self.et_settings.get('auto_calib_pacing'))
        
        if self.et_settings.get('enable_auto_calib'):
            self.tracker.enableAutoCalibration()
        
        if self.et_settings.get('pupil_size_data') == 'diameter':
            self.tracker.setPupilSizeDiameter('YES')
        else:
            self.tracker.setPupilSizeDiameter('NO')

        self.tracker.sendCommand(f"active_eye = {self.et_settings.get('eye').upper()}")

        # TODO: allow settings
        self.tracker.sendCommand("enable_search_limits=YES")
        self.tracker.sendCommand("track_search_limits=YES")
        self.tracker.sendCommand("autothreshold_click=YES")
        self.tracker.sendCommand("autothreshold_repeat=YES")
        self.tracker.sendCommand("enable_camera_position_detect=YES")

        # Probably some more stuff ... 

    def _create_display(self):
        """ Creates display upon initialization . """
        display = PsychopyCustomDisplay(
            self.tracker, self.win, self.settings,
        )
        pylink.openGraphicsEx(display)
        return display

    def calibrate_eyetracker(self):
        """ Starts calibration eyetracker . """
        # Note: doTrackerSetup already calls
        # sendMessage("DISPLAY_COORDS" + win.size)
		# sendCommand("screen_pixel_coords" + win.size)
        self.tracker.doTrackerSetup(*self.win.size)

    def start_recording_eyetracker(self):
        """ Starts recording data. """
        if self.eyetracker_on:
            # TODO: what do those params mean?
            self.tracker.startRecording(1, 1, 1, 1)

    def stop_recording_eyetracker(self):
        """ Stops recording data. """ 
        if self.eyetracker_on:
            self.tracker.stopRecording()

    def close(self):
        """ Closes the session (including eyetracker stuff). """
        super().close()

        if self.eyetracker_on:
            self.tracker.stopRecording()
            self.tracker.setOfflineMode()
            core.wait(.5)
            f_out = op.join(self.output_dir, self.output_str + '.edf')
            self.tracker.receiveDataFile(self.edf_name, f_out)
            self.tracker.close()


class PylinkTrial(Trial):
    # Do we really need a separate class for this?
    # Or should we build this into the regular Trial?
    def run(self):
        """ Sets trialid and calls run of parent class. """
        # This should show (e.g.) different phases and trial nr
        # (but then it should be inside the parent run method)
        self.session.tracker.sendCommand("record_status_message 'TEST!'")
        super().run()


class IOHubEyeTrackerSession(Session):
    """ EyetrackerSession class."""

    def __init__(self, output_str, eyetracker_on=True, **kwargs):
        """ Initializes EyetrackerSession class.
        
        parameters
        ----------
        output_str : str
            Name (string) for output-files (e.g., 'sub-01_ses-post_run-1')
        eyetracker_on : bool
            Whether the eyetracker is actually on
        kwargs : dict
            Extra arguments to base Session class initialization

        attributes
        ----------
        tracker : Eyetracker object
            IOHub or Pylink Eyetracker object
        """
        super().__init__(output_str, **kwargs)
        self.eyetracker_on=eyetracker_on

    def init_eyetracker(self):
        """ Initializes eyetracker.

        After initialization, tracker object ("device" in iohub lingo)
        can be accessed from self.tracker
        """
        if not self.eyetracker_on:
            raise ValueError("Cannot initialize eyetracker if eyetracker_on=False!")

        EYETRACKER_NAME = 'eyetracker.hw.sr_research.eyelink.EyeTracker'
        self.iohub = launchHubServer(
            psychopy_monitor_name=self.monitor.name,
            **{EYETRACKER_NAME: {
                'enable_interface_without_connection': False,
            }}
        )

        self.tracker = self.iohub.devices.eyetracker

    def start_recording_eyetracker(self):
        self.tracker.setRecordingState(True)

    def stop_recording_eyetracker(self):
        self.tracker.setRecordingState(False)

    def calibrate_eyetracker(self):

        if self.tracker is None:
            raise ValueError("Cannot calibrate tracker if it's not initialized yet!")

        self.tracker.runSetupProcedure()

    def close_tracker(self):
        self.stop_recording_eyetracker()
        self.iohub.quit()


class PsychopyCustomDisplay(pylink.EyeLinkCustomDisplay):
    """ Custom display for Eyelink eyetracker.
    Modified from the 'pylinkwrapper' package by Nick DiQuattro
    (https://github.com/ndiquattro/pylinkwrapper). All credits
    go to him.
    """
    def __init__(self, tracker, win, settings):
        super().__init__()
        self.tracker = tracker
        self.win = win
        self.settings = settings  # from session
        self.__target_beep__ = Sound(800, secs=.1)
        self.__target_beep__done__ = Sound(1200, secs=.1)
        self.__target_beep__error__ = Sound(400, secs=.1)
        #self.backcolor = self.win.color

        dot_size_pix = misc.deg2pix(self.settings['eyetracker'].get('dot_size'),
                                    self.win.monitor)
        self.targetout = Circle(
            self.win, pos=(0, 0), radius=dot_size_pix, fillColor='black',
            units='pix', lineColor='black'
        )

        self.targetin = Circle(
            self.win, pos=(0, 0), radius=3, fillColor=0,
            lineColor=0, units='pix', opacity=0
        )
        win.flip()

    def setup_cal_display(self):
        txt = TextStim(
            self.win, text="Please follow the dot. Try not to anticipate its movements.",
            pos=(0, 100), color='black', units='pix'
        )

        txt.draw()
        self.targetout.draw()
        self.win.flip()

    def exit_cal_display(self):
        self.clear_cal_display()

    def clear_cal_display(self):
        self.setup_cal_display()

    def erase_cal_target(self):
        self.win.flip()

    def draw_cal_target(self, x, y):
        # Convert to psychopy coordinates
        x = x - (self.win.size[0] / 2)
        y = -(y - (self.win.size[1] / 2))

        # Set calibration target position
        self.targetout.pos = (x, y)
        self.targetin.pos = (x, y)

        # Display
        self.targetout.draw()
        self.targetin.draw()
        self.win.flip()

    def setup_image_display(self, width, height):

        self.size = (width / 2, height / 2)
        self.clear_cal_display()
        self.last_mouse_state = -1

        # Create array to hold image data later
        if self.rgb_index_array is None:
            self.rgb_index_array = np.zeros((self.size[1], self.size[0]),
                                            dtype=np.uint8)

    def image_title(self, text):
        # Display or update Pupil/CR info on image screen
        if self.imagetitlestim is None:
            self.imagetitlestim = TextStim(self.window,
                                                  text=text,
                                                  pos=(0, self.window.size[
                                                      1] / 2 - 15), height=28,
                                                  color=self.txtcol,
                                                  alignHoriz='center',
                                                  alignVert='top',
                                                  wrapWidth=self.window.size[
                                                                0] * .8,
                                                  units='pix')
        else:
            self.imagetitlestim.setText(text)

    def exit_image_display(self):
        self.clear_cal_display()

    def alert_printf(self, msg):
        print("alert_printf %s" % msg)

    def play_beep(self, beepid):
        if beepid == pylink.DC_TARG_BEEP or beepid == pylink.CAL_TARG_BEEP:
            self.__target_beep__.play()
        elif beepid == pylink.CAL_ERR_BEEP or beepid == pylink.DC_ERR_BEEP:
            self.__target_beep__error__.play()
        else:  # CAL_GOOD_BEEP or DC_GOOD_BEEP
            self.__target_beep__done__.play()

    def get_input_key(self):
            ky = []
            v = event.getKeys()
            for key in v:
                pylink_key = None
                if len(key) == 1:
                    pylink_key = ord(key)
                elif key == "escape":
                    pylink_key = pylink.ESC_KEY
                elif key == "return":
                    pylink_key = pylink.ENTER_KEY
                elif key == "pageup":
                    pylink_key = pylink.PAGE_UP
                elif key == "pagedown":
                    pylink_key = pylink.PAGE_DOWN
                elif key == "up":
                    pylink_key = pylink.CURS_UP
                elif key == "down":
                    pylink_key = pylink.CURS_DOWN
                elif key == "left":
                    pylink_key = pylink.CURS_LEFT
                elif key == "right":
                    pylink_key = pylink.CURS_RIGHT
                else:
                    print(f'Error! :{key} is not a used key.')
                    return

                ky.append(pylink.KeyInput(pylink_key, 0))

            return ky

    def record_abort_hide(self):
        pass
