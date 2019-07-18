import warnings
import os.path as op
import numpy as np
from datetime import datetime
from psychopy import core
from psychopy import misc
from psychopy import event
from psychopy.visual import TextStim, Circle
from psychopy import visual, sound

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

        def setup_image_display(self, width, height):

            self.size = (width / 2, height / 2)
            self.clear_cal_display()
            self.last_mouse_state = -1

            # Create array to hold image data later
            if self.rgb_index_array is None:
                self.rgb_index_array = np.zeros((self.size[1], self.size[0]),
                                                dtype=np.uint8)

        def exit_image_display(self):
            self.clear_cal_display()

        def image_title(self, text):
            # Display or update Pupil/CR info on image screen
            if self.imagetitlestim is None:
                self.imagetitlestim = TextStim(
                    self.window,
                    text=text,
                    pos=(0, self.window.size[1] / 2 - 15),
                    height=28,
                    color=self.txtcol,
                    alignHoriz='center',
                    alignVert='top',
                    wrapWidth=self.window.size[0] * .8,
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
                # Make image
                image = scipy.misc.toimage(self.rgb_index_array,
                                        pal=self.rgb_pallete,
                                        mode='P')
                # Resize Image
                if self.imgstim_size is None:
                    maxsz = self.sres[0] / 2
                    mx = 1.0
                    while (mx + 1) * self.size[0] <= maxsz:
                        mx += 1.0
                    self.imgstim_size = int(self.size[0] * mx), int(
                        self.size[1] * mx)
                image = image.resize(self.imgstim_size)

                # Save image as a temporay file
                tfile = os.path.join(tempfile.gettempdir(), '_eleye.png')
                image.save(tfile, 'PNG')

                # Need this for target distance to show up
                self.__img__ = image
                self.draw_cross_hair()
                self.__img__ = None

                # Create eye image
                if self.eye_image is None:
                    self.eye_image = visual.ImageStim(self.window, tfile,
                                                    size=self.imgstim_size,
                                                    units='pix')
                else:
                    self.eye_image.setImage(tfile)

                # Redraw the Camera Setup Mode graphics
                self.eye_image.draw()
                if self.imagetitlestim:
                    self.imagetitlestim.draw()

                # Display
                self.window.flip()

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
            visual.TextStim(self.window, text='Dummy Connection with EyeLink',
                            color=self.txtcol).draw()
            self.window.flip()

            # Wait for key press
            event.waitKeys()
            self.window.flip()


    class Psychocal(pylink.EyeLinkCustomDisplay):
        def __init__(self, w, h, tracker, window):
            pylink.EyeLinkCustomDisplay.__init__(self)
            self.sres = (w, h)

            # Set up window
            self.window = window
            self.window.flip(clearBuffer=True)
            self.mouse = None

            # Define stimuli
            self.backcolor = window.color
            if sum(window.color) != 0:
                tcolout = -1#-(window.color)
            else:
                tcolout = -1
            self.txtcol = tcolout

            self.targetout = visual.Circle(self.window, pos=(0, 0), radius=10,
                                        fillColor=tcolout,
                                        lineColor=tcolout, units='pix')

            self.targetin = visual.Circle(self.window, pos=(0, 0), radius=3,
                                        fillColor=0,
                                        lineColor=0,
                                        units='pix')

            # Set up sounds
            #self.__target_beep__ = sound.Sound(800, secs=.1)
            #self.__target_beep__done__ = sound.Sound(1200, secs=.1)
            #self.__target_beep__error__ = sound.Sound(400, secs=.1)

            # Image drawing variables (used later)
            self.rgb_index_array = None
            self.imagetitlestim = None
            self.imgstim_size = None
            self.eye_image = None
            self.lineob = None
            self.loz = None

            # Define tracker
            self.setTracker(tracker)

        def setTracker(self, tracker):
            ''' Initial camera set-up for calibration '''

            self.tracker = tracker
            self.tracker_version = tracker.getTrackerVersion()
            if (self.tracker_version >= 3):
                self.tracker.sendCommand("enable_search_limits=YES")
                self.tracker.sendCommand("track_search_limits=YES")
                self.tracker.sendCommand("autothreshold_click=YES")
                self.tracker.sendCommand("autothreshold_repeat=YES")
                self.tracker.sendCommand("enable_camera_position_detect=YES")

        def setup_cal_display(self):
            intxt = 'Please follow the Dot. Try not to anticipate its movements.'
            txtob = visual.TextStim(self.window, intxt, pos=(0, 100),
                                    color=self.txtcol, units='pix')

            txtob.draw()
            self.targetout.draw()
            self.window.flip()

        def exit_cal_display(self):
            self.clear_cal_display()

        def record_abort_hide(self):
            pass

        def clear_cal_display(self):
            self.setup_cal_display()

        def erase_cal_target(self):
            self.window.flip()

        def draw_cal_target(self, x, y):
            # Convert to psychopy coordinates
            x = x - (self.sres[0] / 2)
            y = -(y - (self.sres[1] / 2))

            # Set calibration target position
            self.targetout.pos = (x, y)
            self.targetin.pos = (x, y)

            # Display
            self.targetout.draw()
            self.targetin.draw()
            self.window.flip()

        def play_beep(self, beepid):
            if beepid == pylink.DC_TARG_BEEP or beepid == pylink.CAL_TARG_BEEP:
                self.__target_beep__.play()
            elif beepid == pylink.CAL_ERR_BEEP or beepid == pylink.DC_ERR_BEEP:
                self.__target_beep__error__.play()
            else:  # CAL_GOOD_BEEP or DC_GOOD_BEEP
                self.__target_beep__done__.play()

        def getColorFromIndex(self, colorindex):
            if colorindex == pylink.CR_HAIR_COLOR:
                return (1, 1, 1)
            elif colorindex == pylink.PUPIL_HAIR_COLOR:
                return (1, 1, 1)
            elif colorindex == pylink.PUPIL_BOX_COLOR:
                return (-1, 1, -1)
            elif colorindex == pylink.SEARCH_LIMIT_BOX_COLOR:
                return (1, -1, -1)
            elif colorindex == pylink.MOUSE_CURSOR_COLOR:
                return (1, -1, -1)
            else:
                return (-1, -1, -1)

        def draw_line(self, x1, y1, x2, y2, colorindex):
            pass

        # 		# Convert to psychopy coordinates
        # 		x1 = x1 - (self.sres[0] / 2)
        # 		x2 = x2 - (self.sres[0] / 2)
        # 		y1 = -(y1 - (self.sres[1] / 2))
        # 		y2 = -(y2 - (self.sres[1] / 2))
        #
        # 		#Convert to image centerted x,y
        # 		x1 = int((float(x1) / float(self.size[0])) * self.imgstim_size[0])
        # 		x2 = int((float(x2) / float(self.size[0])) * self.imgstim_size[0])
        # 		y1 = int((float(y1) / float(self.size[1])) * self.imgstim_size[1])
        # 		y2 = int((float(y2) / float(self.size[1])) * self.imgstim_size[1])
        #
        # 		# Get Color
        # 		linecol = self.getColorFromIndex(colorindex)
        #
        # 		# Define object
        # 		if self.lineob is None:
        # 			self.lineob = visual.Line(self.window, (x1, y1), (x2, y2),
        # 									lineColor = linecol,
        # 									units = 'pix')
        # 		else:
        # 			self.lineob.setLineColor(linecol)
        # 			self.lineob.setStart = (x1, y1)
        # 			self.lineob.setEnd = (x2, y2)
        #
        # 		#Draw
        # 		self.lineob.draw()

        def draw_lozenge(self, x, y, width, height, colorindex):
            pass

        # 		# Convert to psychopy coordinates
        # 		x = x - (self.sres[0] / 2)
        # 		y = -(y - (self.sres[1] / 2))
        #
        # 		# Convert to image centered coords
        # 		x = int((float(x) / float(self.size[0])) * self.imgstim_size[0])
        # 		width = int((float(width) / float(self.size[0])) * self.imgstim_size[0])
        # 		y = int((float(y) / float(self.size[1])) * self.imgstim_size[1])
        # 		height = int((float(height)/float(self.size[1])) * self.imgstim_size[1])
        # 		#print width, height
        #
        # 		# Get Color
        # 		lozcol = self.getColorFromIndex(colorindex)
        #
        # 		x = 0
        # 		y = 0
        #
        # 		# Draw objects
        # 		if width > height:
        # 			rad = height/2
        #
        # 			# draw the lines
        # 			visual.Line(self.window, (x+rad, y), (x+width-rad, y),
        # 						lineColor = lozcol, units = 'pix').draw()
        # 			visual.Line(self.window, (x+rad, y+height), (x+width-rad, y+height),
        # 						lineColor = lozcol, units = 'pix').draw()
        #
        # 			# draw semicircles
        # 			pos = (x+rad, y+rad)
        # 			visual.Circle(self.window, rad, pos = pos,
        # 							fillColor = lozcol, units = 'pix').draw()
        #
        # 			pos = ((x+width)-rad, y+rad)
        # 			visual.Circle(self.window, rad, pos = pos,
        # 							fillColor = lozcol, units = 'pix').draw()
        # 		else:
        # 			rad = width/2
        #
        # 			#draw the lines
        # 			visual.Line(self.window, (x, y+rad), (x, y+height-rad),
        # 						lineColor = lozcol, units = 'pix').draw()
        # 			visual.Line(self.window, (x+width, y+rad), (x+width, y+height-rad),
        # 						lineColor = lozcol, units = 'pix').draw()
        #
        # 			#draw semicircles
        # 			if rad == 0:
        # 				return #cannot draw sthe circle with 0 radius
        # 			pos = (x+rad, y+rad)
        # 			visual.Circle(self.window, rad, pos = pos,
        # 							fillColor = lozcol, units = 'pix').draw()
        #
        # 			pos = (x+rad, y+height-rad)
        # 			visual.Circle(self.window, rad, pos = pos,
        # 							fillColor = lozcol, units = 'pix').draw()


        def get_mouse_state(self):
            pass

        # 		# Estabish mouse
        # 		if self.mouse is None:
        # 			self.mouse = event.Mouse()
        #
        # 		# Get mouse state
        # 		mpos = self.mouse.getPos()
        # 		mpre = self.mouse.getPressed()
        #
        # 		# Convert mpos to EyeLink coordinates
        # 		mpos = [int(deg2pix(x, self.window.monitor)) for x in mpos]
        # 		mpos = (int(mpos[0] + (self.sres[0] / 2)),
        # 				int(mpos[1] + (self.sres[1] / 2)))
        #
        # 		# Return
        # 		return (mpos, mpre[0])

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
                    print('Error! :{} is not a used key.'.format(key))
                    return

                ky.append(pylink.KeyInput(pylink_key, 0))

            return ky

        def exit_image_display(self):
            self.clear_cal_display()

        def alert_printf(self, msg):
            print("alert_printf %s" % msg)

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
                self.imagetitlestim = visual.TextStim(self.window,
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

        def draw_image_line(self, width, line, totlines, buff):
            # Get image info for each line of image
            for i in range(width):
                self.rgb_index_array[line - 1, i] = buff[i]

            # Once all lines are collected turn into an image to display
            if line == totlines:
                # Make image
                image = scipy.misc.toimage(self.rgb_index_array,
                                        pal=self.rgb_pallete,
                                        mode='P')
                # Resize Image
                if self.imgstim_size is None:
                    maxsz = self.sres[0] / 2
                    mx = 1.0
                    while (mx + 1) * self.size[0] <= maxsz:
                        mx += 1.0
                    self.imgstim_size = int(self.size[0] * mx), int(
                        self.size[1] * mx)
                image = image.resize(self.imgstim_size)

                # Save image as a temporay file
                tfile = os.path.join(tempfile.gettempdir(), '_eleye.png')
                image.save(tfile, 'PNG')

                # Need this for target distance to show up
                self.__img__ = image
                self.draw_cross_hair()
                self.__img__ = None

                # Create eye image
                if self.eye_image is None:
                    self.eye_image = visual.ImageStim(self.window, tfile,
                                                    size=self.imgstim_size,
                                                    units='pix')
                else:
                    self.eye_image.setImage(tfile)

                # Redraw the Camera Setup Mode graphics
                self.eye_image.draw()
                if self.imagetitlestim:
                    self.imagetitlestim.draw()

                # Display
                self.window.flip()

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
            visual.TextStim(self.window, text='Dummy Connection with EyeLink',
                            color=self.txtcol).draw()
            self.window.flip()

            # Wait for key press
            event.waitKeys()
            self.window.flip()
