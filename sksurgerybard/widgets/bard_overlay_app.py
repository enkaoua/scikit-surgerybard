# coding=utf-8

""" Overlay class for the BARD application."""

import os
import numpy as np
import cv2
import cv2.aruco as aruco

from sksurgerycore.transforms.transform_manager import TransformManager
from sksurgerycore.configuration.configuration_manager import \
        ConfigurationManager
from sksurgeryvtk.utils.matrix_utils import create_vtk_matrix_from_numpy
from sksurgeryvtk.models.vtk_sphere_model import VTKSphereModel
from sksurgeryutils.common_overlay_apps import OverlayBaseApp
from sksurgeryarucotracker.arucotracker import ArUcoTracker
from sksurgerybard.algorithms.bard_config_algorithms import configure_bard, \
    configure_interaction
from sksurgerybard.algorithms.bard_config_speech import \
    configure_speech_interaction
from sksurgerybard.algorithms.visualisation import BardVisualisation
from sksurgerybard.algorithms.pointer import BardPointerWriter

# pylint: disable=too-many-instance-attributes, too-many-branches

def setup_tracker(configuration, calib_dir = None):
    """
    BARD Internal function to configure an ArUco tracker
    and return a tracker object. Could be modified to set
    up another sksurgery tracker (e.g. nditracker)
    """
    tracker_config = {}
    rigid_bodies = []
    model_config = configuration.get('models', None)
    if model_config is not None:
        ref_filename = model_config.get('ref_file', None)
        if ref_filename is None:
            raise ValueError("Model configuration does not include ref_file")

        rigid_bodies.append({
                'name' : 'reference',
                'filename' : ref_filename,
                'aruco dictionary' : 'DICT_ARUCO_ORIGINAL'
                })

    pointer_config = configuration.get('pointerData', None)
    if pointer_config is not None:
        pointer_filename = pointer_config.get('pointer_tag_file', None)
        if pointer_filename is None:
            raise ValueError("Pointer config does not include pointer_tag_file")

        rigid_bodies.append({
                'name' : 'pointer',
                'filename' : pointer_filename,
                'aruco dictionary' : 'DICT_ARUCO_ORIGINAL'
                })

    tracker_config['rigid bodies'] = rigid_bodies

    _video_source, mtx33d, dist5d, _dims, _, _, _, _, _, _, _, _, _, \
                    = configure_bard(configuration, calib_dir)
    tracker_config['video source'] = 'none'
    tracker_config['camera projection'] = mtx33d
    tracker_config['camera distortion'] = dist5d
    tracker_config['aruco dictionary'] = 'DICT_4X4_50'
    tracker_config['smoothing buffer'] = 3

    return ArUcoTracker(tracker_config)

class BARDOverlayApp(OverlayBaseApp):
    """
    Inherits from OverlayBaseApp, and adds methods to
    detect aruco tags and move the model to follow.
    """
    def __init__(self, config_file, calib_dir):
        """
        Overrides the default constructor to add some member variables
        which we need for the aruco tag detection.
        """
        self._speech_int = None
        configurer = ConfigurationManager(config_file)
        configuration = configurer.get_copy()

        # Loads all config from file.
        (video_source, mtx33d, dist15d, ref_data, modelreference2model,
         pointer_ref, models_path, pointer_tip, outdir, dims, interaction,
         visible_anatomy,
         speech_config) = configure_bard(configuration, calib_dir)

        self.dims = dims
        self.mtx33d = mtx33d
        self.dist15d = dist15d

        self.tracker = setup_tracker(configuration)
        self.tracker.start_tracking()

        self.dictionary = aruco.getPredefinedDictionary(aruco.
                                                        DICT_ARUCO_ORIGINAL)

        self.transform_manager = TransformManager()

        self.transform_manager.add("model2modelreference", modelreference2model)

        if pointer_ref is not None:
            self.transform_manager.add("pointerref2camera",
                                       np.eye(4, dtype = np.float64))

        # call the constructor for the base class
        super().__init__(video_source, dims)

        # This sets the camera calibration matrix to a matrix that was
        # either read in from command line or from config, or a reasonable
        # default for a 640x480 webcam.
        self.vtk_overlay_window.set_camera_matrix(mtx33d)

        # start things off with the camera at the origin.
        camera2modelreference = np.identity(4)
        self.transform_manager.add("camera2modelreference",
                                   camera2modelreference)
        camera2modelreference = self.transform_manager.get(
                        "camera2modelreference")
        self.vtk_overlay_window.set_camera_pose(camera2modelreference)

        if not os.path.isdir(outdir):
            os.mkdir(outdir)

        self._pointer_writer = BardPointerWriter(
                        self.transform_manager, outdir, pointer_tip)
        self._resize_flag = True

        if models_path:
            self.add_vtk_models_from_dir(models_path)

        matrix = create_vtk_matrix_from_numpy(modelreference2model)
        self._model_list = {'visible anatomy' : 0,
                            'target anatomy' : 0,
                            'reference' : 0,
                            'pointers' : 0}

        self._model_list['visible anatomy'] = visible_anatomy

        for index, actor in enumerate(self._get_all_actors()):
            actor.SetUserMatrix(matrix)
            if index >= visible_anatomy:
                self._model_list['target anatomy'] = \
                                self._model_list.get('target anatomy') + 1

        if ref_data is not None:
            model_reference_spheres = VTKSphereModel(
                ref_data[:, 1:4], radius=5.0)
            self.vtk_overlay_window.add_vtk_actor(model_reference_spheres.actor)
            self._model_list['reference'] = 1

        if pointer_ref is not None:
            pointer_reference_spheres = VTKSphereModel(
                pointer_ref[:, 1:4], radius=5.0)
            self.vtk_overlay_window.add_vtk_actor(
                pointer_reference_spheres.actor)
            self._model_list['pointers'] = self._model_list.get('pointers') + 1

        if pointer_tip is not None:
            pointer_tip_sphere = VTKSphereModel(pointer_tip, radius=3.0)
            self.vtk_overlay_window.add_vtk_actor(pointer_tip_sphere.actor)
            self._model_list['pointers'] = self._model_list.get('pointers') + 1

        bard_visualisation = BardVisualisation(self._get_all_actors(),
                                               self._model_list)

        configure_interaction(interaction, self.vtk_overlay_window,
                              self._pointer_writer, bard_visualisation)

        if interaction.get('speech', False):
            self._speech_int = configure_speech_interaction(
                speech_config, bard_visualisation)

    def __del__(self):
        if self._speech_int is not None:
            self._speech_int.stop_listener()

    def update(self):
        """
        Update the background render with a new frame and
        scan for aruco tags.
        """
        _, image = self.video_source.read()

        undistorted = cv2.undistort(image, self.mtx33d, self.dist15d)

        self._update_tracking(image)
        self._update_overlay_window()

        self.vtk_overlay_window.set_video_image(undistorted)

        if self._resize_flag:
            if self.dims:
                self.vtk_overlay_window.resize(self.dims[0], self.dims[1])
            self._resize_flag = False

        self.vtk_overlay_window.Render()

    def _update_tracking(self, image):
        """
        Internal method to update the transform manager with
        up to date versions of the required transforms. Image
        is only used if we're using an ArUcoTracker
        """
        tracking = []
        if isinstance(self.tracker, ArUcoTracker):
            port_handles, _timestamps, _framenumbers, tracking, quality = \
                        self.tracker.get_frame(image)
        else:
            port_handles, _timestamps, _framenumbers, tracking, quality = \
                        self.tracker.get_frame()

        try:
            reference_index = port_handles.index('reference')
            if ((not np.isnan(quality[reference_index])) and
                quality[reference_index] > 0.2):
                modelreference2camera = tracking[reference_index]
                self.transform_manager.add("modelreference2camera",
                                           modelreference2camera)
        except ValueError:
            pass


        try:
            pointer_index = port_handles.index('pointer')
            if ((not np.isnan(quality[pointer_index])) and
                quality[pointer_index] > 0.2):
                pointerref2camera = tracking[pointer_index]
                self.transform_manager.add("pointerref2camera",
                                           pointerref2camera)
        except ValueError:
            pass


    def _update_overlay_window(self):
        """
        Internal method to update the overlay window with
        latest pose estimates
        """
        camera2modelreference = self.transform_manager.get(
                        "camera2modelreference")
        self.vtk_overlay_window.set_camera_pose(camera2modelreference)

        actors = self._get_pointer_actors()
        if len(actors) > 0:
            ptrref2modelref = self.transform_manager.get(
                                    "pointerref2modelreference")
            matrix = create_vtk_matrix_from_numpy(ptrref2modelref)
            for actor in actors:
                actor.SetUserMatrix(matrix)

    def _get_pointer_actors(self):
        actors = self._get_all_actors()
        no_actors = actors.GetNumberOfItems()
        return_actors = []
        for index, actor in enumerate(actors):
            if index >= no_actors - self._model_list.get('pointers'):
                return_actors.append(actor)
        return return_actors

    def _get_all_actors(self):
        return self.vtk_overlay_window.foreground_renderer.GetActors()
