import warnings
import os.path as op
import numpy as np
from datetime import datetime
from psychopy import core
from psychopy import misc
from psychopy import event
from psychopy.visual import TextStim, Circle
from psychopy import visual, sound
from psychopy import logging
from PIL import Image, ImageOps
from .session import Session
from .trial import Trial


try:
    import pylink
except ModuleNotFoundError:
    msg = "Pylink is not installed! Eyetracker cannot be used"
    warnings.warn(msg)
    PYLINK_AVAILABLE = False
else:
    PYLINK_AVAILABLE = True    


class PylinkEyetrackerSession(Session):
    """ Custom PylinkEyetrackerSession class. """
    def __init__(self, output_str, output_dir, settings_file, eyetracker_on=True):
        """ Initializes PylinkEyetrackerSession class.
        
        Parameters
        ----------
        output_str : str
            Name (string) for output-files (e.g., 'sub-01_ses-post_run-1')
        eyetracker_on : bool
            Whether the eyetracker is actually on
        kwargs : dict
            Extra arguments to base Session class initialization

        Attributes
        ----------
        tracker : Eyelink
            Pylink 'Eyelink' object
        display : PsychopyCustomDisplay
            exptools2' PsychopyCustomDisplay object
        """
        super().__init__(output_str, output_dir, settings_file)
        self.eyetracker_on = eyetracker_on
        self.et_settings = self.settings['eyetracker']  # for convenience
        self.tracker = self._create_tracker()
        self.display = self._create_display()
        self._set_options_tracker()

    def _create_tracker(self):
        """ Creates tracker object upon initialization. """
        if not self.eyetracker_on or not PYLINK_AVAILABLE:
            return None

        tracker = pylink.EyeLink(self.et_settings.get('address'))
        pylink.flushGetkeyQueue()
        tracker.setOfflineMode()
        tracker.sendCommand('set_idle_mode')  # why?

        self.edf_name = datetime.now().strftime('%H_%M_%S.edf')
        tracker.openDataFile(self.edf_name)
        return tracker

    def _set_options_tracker(self):
        """ Sets a bunch of options . """

        if self.eyetracker_on:
            for opt_name, opt_val in self.et_settings['options'].items():
                cmd = f'{opt_name} = {opt_val}'
                self.tracker.sendCommand(cmd)
                core.wait(0.05)  # give it some time

    def _create_display(self):
        """ Creates a custom display upon initialization ."""
        
        if not self.eyetracker_on or not PYLINK_AVAILABLE:
            return None

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
        """ Starts recording data. This should be called 
        *before* calling self.start_experiment()
        """
        if self.eyetracker_on:
            self.tracker.startRecording(1, 1, 1, 1)
            core.wait(0.05)  # start recording takes a while

    def stop_recording_eyetracker(self):
        """ Stops recording data. """ 
        if self.eyetracker_on:
            core.wait(0.15)  # wait a bit
            self.tracker.stopRecording()

    def close(self):
        """ Closes the session (including eyetracker stuff). """
        super().close()

        if self.eyetracker_on:
            self.stop_recording_eyetracker()
            self.tracker.setOfflineMode()
            core.wait(.5)
            f_out = op.join(self.output_dir, self.output_str + '.edf')
            self.tracker.receiveDataFile(self.edf_name, f_out)
            self.tracker.close()


if PYLINK_AVAILABLE:  # super ugly, but don't know an elegant fix atm

    class PsychopyCustomDisplay(pylink.EyeLinkCustomDisplay):
        """ Custom display for Eyelink eyetracker.
        Modified from the 'pylinkwrapper' package by Nick DiQuattro
        (https://github.com/ndiquattro/pylinkwrapper). All credits
        go to him.
        """
        def __init__(self, tracker, win, settings):
            """ Initializes PsychopyCustomDisplay object.

            """
            super().__init__()
            self.tracker = tracker
            self.win = win
            self.settings = settings  # from session
            self.txtcol = -1
            #self.__target_beep__ = sound.Sound(800, secs=.1)  # THIS WILL GIVE A SEGFAULT!
            #self.__target_beep__done__ = sound.Sound(1200, secs=.1)  # THIS WILL GIVE A SEGFAULT!
            #self.__target_beep__error__ = sound.Sound(400, secs=.1)  # THIS WILL GIVE A SEGFAULT!
            self.backcolor = self.win.color

            self.imgstim_size = None
            self.rgb_index_array = None
            self.eye_image = None
            self.imagetitlestim = None

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

        def alert_printf(self, msg):
            print("alert_printf %s" % msg)

        def play_beep(self, beepid):
            if beepid == pylink.DC_TARG_BEEP or beepid == pylink.CAL_TARG_BEEP:
                #self.__target_beep__.play()
                pass
            elif beepid == pylink.CAL_ERR_BEEP or beepid == pylink.DC_ERR_BEEP:
                #self.__target_beep__error__.play()
                pass
            else:  # CAL_GOOD_BEEP or DC_GOOD_BEEP
                #self.__target_beep__done__.play()
                pass

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
        def setup_image_display(self, width, height):
            """Initialize the index array that will contain camera image data."""

            if width and height:
                self.eye_frame_size = (width, height)
                self.clear_cal_display()
                self.last_mouse_state = -1
                if self.rgb_index_array is None:
                    self.rgb_index_array = np.zeros((int(height/2), int(width/2)), dtype=np.uint8)

        def exit_image_display(self):
            self.clear_cal_display()

        def image_title(self, text):
            # Display or update Pupil/CR info on image screen
            if self.imagetitlestim is None:
                self.imagetitlestim = TextStim(
                    self.win,
                    text=text,
                    pos=(0, self.win.size[1] / 2 - 15),
                    height=28,
                    color=self.txtcol,
                    alignHoriz='center',
                    alignVert='top',
                    wrapWidth=self.win.size[0] * .8,
                    units='pix'
                )
            else:
                self.imagetitlestim.setText(text)

        def exit_image_display(self):
            self.clear_cal_display()


        def draw_image_line(self, width, line, totlines, buff):
            # Get image info for each line of image
            for i in range(width):
                self.rgb_index_array[line - 1, i] = buff[i]

            # Once all lines are collected turn into an image to display
            if line == totlines:
                try:
                    image = Image.fromarray(self.rgb_index_array,
                                            mode='P')
                    image.putpalette(self.rgb_pallete)
                    image = ImageOps.fit(image, [640, 480])
                    if self.eye_image is None:
                        self.eye_image = visual.ImageStim(
                            self.win, image)
                    else:
                        self.eye_image.setImage(image)

                    # Redraw the Camera Setup Mode graphics
                    #self.blankdisplay.draw()
                    self.eye_image.draw()
                    if self.imagetitlestim:
                        self.imagetitlestim.draw()
                    self.win.flip()

                except Exception as err:
                    logging.warning('Error during eye image display: ', err)

        def set_image_palette(self, r, g, b):
            # This does something the other image functions need
            self.clear_cal_display()
            sz = len(r)
            self.rgb_pallete = np.zeros((sz, 3), dtype=np.uint8)
            i = 0
            while i < sz:
                self.rgb_pallete[i:] = int(r[i]), int(g[i]), int(b[i])
                i += 1

        def dummynote(self):
            # Draw Text
            visual.TextStim(self.win, text='Dummy Connection with EyeLink',
                            color=self.txtcol).draw()
            self.win.flip()

            # Wait for key press
            event.waitKeys()
            self.win.flip()