from psychopy.iohub import launchHubServer
from psychopy.visual import Window

EYETRACKER_CLASS_PATH = 'eyetracker.hw.sr_research.eyelink.EyeTracker'

display_cfg = {
    'name': 'display',
    'reporting_unit_type': 'pix',
    'device_number': 0,
    'physical_dimensions': {
        'width': 500,
        'height': 281,
        'unit_type': 'mm'
    },
    'default_eye_distance': {
        'surface_center': 550,
        'unit_type': 'mm'
    }
}

eyetracker_cfg = {
    'name': 'tracker',
    'enable': True,
    'stream_events': True,
    'auto_report_events': False,
    'event_buffer_length': 1024,
    'device_timer': {
        'interval': 0.001
    },
    'monitor_event_types': [
        'MonocularEyeSampleEvent',
        'BinocularEyeSampleEvent',
        'FixationStartEvent',
        'FixationEndEvent',
        'SaccadeStartEvent',
        'SaccadeEndEvent',
        'BlinkStartEvent',
        'BlinkEndEvent'
    ],
    'calibration': {
        'type': 'NINE_POINTS',
        'auto_pace': True,
        'pacing_speed': 1.5,
        'screen_background_color': [128,128,128], # RGB
        'target_type': 'CIRCLE_TARGET',
        'target_attributes': {
            'out_diameter': 33,
            'inner_diameter': 6,
            'outer_color': [255, 255, 255],
            'inner_color': [0, 0, 0]
        }
    },
    'network_settings': '100.1.1.1',
    'default_native_data_file_name': 'et_data',
    'simulation_mode': False,
    'enable_interface_without_connection': False,
    'runtime_settings': {
        'sampling_rate': 250,
        'track_eyes': 'RIGHT_EYE',
        'sample_filtering': {
            'FILTER_FILE': 'FILTER_LEVEL_2',
            'FILTER_ONLINE': 'FILTER_LEVEL_OFF'
        },
        'vog_settings': {
            'pupil_measure_types': 'PUPIL_AREA',
            'tracker_mode': 'PUPIL_CR_TRACKING',
            'pupil_center_algorithm': 'ELLIPSE_FIT'

        }
    },
    'model_name': 'EYELINK 1000 DESKTOP',
    'manufacturer_name': 'SR Research Ltd.',
    'device_number': 0
}

launchHubServer(Display=display_cfg)#, **{EYETRACKER_CLASS_PATH: eyetracker_cfg})
win = Window()
win.flip()


