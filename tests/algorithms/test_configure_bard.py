#  -*- coding: utf-8 -*-

""" Tests for BARD configuration module. """

from os.path import join
import numpy as np
import pytest
import sksurgerybard.algorithms.bard_config_algorithms as bca


def test_valid_config():
    """
    config, and checks that we have retrieved the calibration
    """
    config = {
        "camera": {
        "source": 0,
        "window size": [640, 480],
        "calibration directory": "data/calibration/matts_mbp_640_x_480"
        },
        "models": {
            "models_dir": "data/PelvisPhantom/",
            "ref_file": "data/reference.txt",
            "reference_to_model" : "data/id.txt",
            "tag_width": 49.5
        }
    }

    _, _, _, _, _, _, _, _, _ = bca.configure_bard(config)

    config = None
    with pytest.raises(AttributeError):
        _, _, _, _, _, _,_, _, _ = bca.configure_bard(config)


def test_configure_camera():
    """Tests for the camera configuration"""
    config = {
        "camera": {
        "source": 0,
        "window size": [640, 480],
        "calibration directory": "data/calibration/matts_mbp_640_x_480"
        },
        "models": {
            "models_dir": "data/PelvisPhantom/",
            "ref_file": "data/reference.txt",
            "reference_to_model" : "data/id.txt",
            "tag_width": 49.5
        }
    }

    video_source, mtx33d, dist15d, dims = bca.configure_camera(config)

    # Just a test to check we have loaded the calibration.
    assert video_source == 0
    assert mtx33d is not None
    assert np.isclose(mtx33d[0][0], 608.67179504)
    assert dist15d is not None
    assert np.isclose(dist15d[0], -0.02191634)
    assert dims == (640, 480)

    config = None
    video_source, mtx33d, dist15d, dims = bca.configure_camera(config)
    assert video_source == 0
    r_mtx33d = np.array([1000.0, 0.0, 320.0, 0.0, 1000.0, 240.0, 0.0, 0.0, 1.0])
    r_mtx33d = np.reshape(mtx33d, (3, 3))
    assert np.array_equal(mtx33d, r_mtx33d)
    assert np.array_equal(dist15d, np.array([0.0, 0.0, 0.0, 0.0, 0.0]))
    assert dims is None


def test_get_calibration_filenames():
    """Tests for get_calibration_filenames"""

    calib_dir = 'data'
    with pytest.raises(FileNotFoundError):
        bca.get_calibration_filenames(calib_dir)

    calib_dir = 'data/calibration/matts_mbp_640_x_480'
    intrins, dist = bca.get_calibration_filenames(calib_dir)

    assert intrins == \
        join(calib_dir, 'calib.intrinsics.txt')
    assert dist == \
        join(calib_dir, 'calib.distortion.txt')


def test_replace_calib_dir():
    """
    Tests that replace_calibration_dir works as intended
    """
    #empty configuration
    config_in = None
    calibration_dir = None
    config_out = bca.replace_calibration_dir(config_in, calibration_dir)
    assert config_out is None

    #non empty configuration
    config_in = 'test config'
    calibration_dir = None
    config_out = bca.replace_calibration_dir(config_in, calibration_dir)
    assert config_out == config_in

    #empty config, non empty calib_dir
    config_in = None
    calibration_dir = 'test_string'
    config_out = bca.replace_calibration_dir(config_in, calibration_dir)
    assert config_out is not None
    camera_config = config_out.get('camera', None)
    assert camera_config is not None
    assert camera_config.get('calibration directory', None) == 'test_string'

    #with tracker config using a different camera
    config_in = {
                    'camera' : {
                                'source' : 1,
                                'calibration directory' : 'overwrite this',
                                'other property' : 'do not overwrite'
                                },
                    'tracker' :
                                {
                                  'type' : 'sksaruco',
                                  'video source': 0,
                                  'calibration directory' : 'do not overwrite'
                                }
                }
    calibration_dir = 'test_string'
    config_out = bca.replace_calibration_dir(config_in, calibration_dir)
    camera_config = config_out.get('camera', None)
    assert camera_config.get('calibration directory', None) == 'test_string'
    assert camera_config.get('other property', None) == 'do not overwrite'
    tracker_config = config_out.get('tracker', None)
    assert tracker_config.get('calibration directory', None) == \
                    'do not overwrite'

    #with tracker config using the same camera
    config_in = {
                    'camera' : {
                                'source' : 1,
                                'calibration directory' : 'overwrite this',
                                },
                    'tracker' :
                                {
                                  'type' : 'sksaruco',
                                  'video source': 1,
                                  'calibration directory' : 'overwrite this'
                                }
                }
    calibration_dir = 'test_string'
    config_out = bca.replace_calibration_dir(config_in, calibration_dir)
    camera_config = config_out.get('camera', None)
    assert camera_config.get('calibration directory', None) == 'test_string'
    tracker_config = config_out.get('tracker', None)
    assert tracker_config.get('calibration directory', None) == \
                    'test_string'
