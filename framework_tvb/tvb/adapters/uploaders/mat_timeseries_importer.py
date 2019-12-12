# -*- coding: utf-8 -*-
#
#
# TheVirtualBrain-Framework Package. This package holds all Data Management, and 
# Web-UI helpful to run brain-simulations. To use it, you also need do download
# TheVirtualBrain-Scientific Package (for simulators). See content of the
# documentation-folder for more details. See also http://www.thevirtualbrain.org
#
# (c) 2012-2020, Baycrest Centre for Geriatric Care ("Baycrest") and others
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE.  See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this
# program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#   CITATION:
# When using The Virtual Brain for scientific publications, please cite it as follows:
#
#   Paula Sanz Leon, Stuart A. Knock, M. Marmaduke Woodman, Lia Domide,
#   Jochen Mersmann, Anthony R. McIntosh, Viktor Jirsa (2013)
#       The Virtual Brain: a simulator of primate brain network dynamics.
#   Frontiers in Neuroinformatics (7:10. doi: 10.3389/fninf.2013.00010)
#
#

"""
.. moduleauthor:: Mihai Andrei <mihai.andrei@codemart.ro>
"""
import json
import uuid
import numpy
from tvb.basic.neotraits.api import Attr
from tvb.core.neotraits.view_model import ViewModel, UploadAttr, DataTypeGidAttr
from tvb.datatypes.connectivity import Connectivity
from tvb.datatypes.time_series import TimeSeriesRegion, TimeSeriesEEG
from tvb.adapters.uploaders.mat.parser import read_nested_mat_file
from tvb.core.adapters.exceptions import ParseException, LaunchException
from tvb.core.adapters.abcuploader import ABCUploader, ABCUploaderForm
from tvb.adapters.datatypes.h5.time_series_h5 import TimeSeriesRegionH5, TimeSeriesEEGH5
from tvb.adapters.datatypes.db.time_series import TimeSeriesRegionIndex, TimeSeriesEEGIndex
from tvb.core.entities.storage import transactional
from tvb.core.adapters.arguments_serialisation import parse_slice
from tvb.core.neotraits.forms import TraitUploadField, StrField, BoolField, IntField, TraitDataTypeSelectField
from tvb.core.neotraits.db import prepare_array_shape_meta
from tvb.core.neocom import h5

TS_REGION = "Region"
TS_EEG = "EEG"


class MatTimeSeriesImporterModel(ViewModel):
    data_file = UploadAttr(
        field_type=str,
        label='Please select file to import'
    )

    dataset_name = Attr(
        field_type=str,
        label='Matlab dataset name',
        doc='Name of the MATLAB dataset where data is stored'
    )

    structure_path = Attr(
        field_type=str,
        required=False,
        default='',
        label='For nested structures enter the field path (separated by .)'
    )

    transpose = Attr(
        field_type=bool,
        required=False,
        default=False,
        label='Transpose the array. Expected shape is (time, channel)'
    )

    slice = Attr(
        field_type=str,
        required=False,
        default='',
        label='Slice of the array in numpy syntax. Expected shape is (time, channel)'
    )

    sampling_rate = Attr(
        field_type=int,
        required=False,
        default=100,
        label='sampling rate (Hz)'
    )

    start_time = Attr(
        field_type=int,
        default=0,
        label='starting time (ms)'
    )


class MatTimeSeriesImporterForm(ABCUploaderForm):

    def __init__(self, prefix='', project_id=None):
        super(MatTimeSeriesImporterForm, self).__init__(prefix, project_id)
        self.data_file = TraitUploadField(MatTimeSeriesImporterModel.data_file, '.mat', self, name='data_file')
        self.dataset_name = StrField(MatTimeSeriesImporterModel.dataset_name, self, name='dataset_name')
        self.structure_path = StrField(MatTimeSeriesImporterModel.structure_path, self, name='structure_path')
        self.transpose = BoolField(MatTimeSeriesImporterModel.transpose, self, name='transpose')
        self.slice = StrField(MatTimeSeriesImporterModel.slice, self, name='slice')
        self.sampling_rate = IntField(MatTimeSeriesImporterModel.sampling_rate, self, name='sampling_rate')
        self.start_time = IntField(MatTimeSeriesImporterModel.start_time, self, name='start_time')


class RegionMatTimeSeriesImporterModel(ViewModel):
    region = DataTypeGidAttr(
        linked_datatype=Connectivity,
        label='Connectivity'
    )


class RegionMatTimeSeriesImporterForm(MatTimeSeriesImporterForm):

    def __init__(self, prefix='', project_id=None):
        super(RegionMatTimeSeriesImporterForm, self).__init__(prefix, project_id)
        self.region = TraitDataTypeSelectField(RegionMatTimeSeriesImporterModel.region, self, name='tstype_parameters')


class MatTimeSeriesImporter(ABCUploader):
    """
    Import time series from a .mat file.
    """
    _ui_name = "Timeseries Region MAT"
    _ui_subsection = "mat_ts_importer"
    _ui_description = "Import time series from a .mat file."
    tstype = TS_REGION

    def get_form_class(self):
        return RegionMatTimeSeriesImporterForm

    def get_output(self):
        return [TimeSeriesRegionIndex, TimeSeriesEEGIndex]

    def create_region_ts(self, data_shape, connectivity):
        if connectivity.number_of_regions != data_shape[1]:
            raise LaunchException("Data has %d channels but the connectivity has %d nodes"
                                  % (data_shape[1], connectivity.number_of_regions))
        ts_idx = TimeSeriesRegionIndex()
        ts_idx.connectivity_gid = connectivity.gid
        ts_idx.has_surface_mapping = True

        ts_h5_path = h5.path_for(self.storage_path, TimeSeriesRegionH5, ts_idx.gid)
        ts_h5 = TimeSeriesRegionH5(ts_h5_path)
        ts_h5.connectivity.store(uuid.UUID(connectivity.gid))

        return TimeSeriesRegion(), ts_idx, ts_h5

    def create_eeg_ts(self, data_shape, sensors):
        if sensors.number_of_sensors != data_shape[1]:
            raise LaunchException("Data has %d channels but the sensors have %d"
                                  % (data_shape[1], sensors.number_of_sensors))

        ts_idx = TimeSeriesEEGIndex()
        ts_idx.sensors_gid = sensors.gid

        ts_h5_path = h5.path_for(self.storage_path, TimeSeriesEEGH5, ts_idx.gid)
        ts_h5 = TimeSeriesEEGH5(ts_h5_path)
        ts_h5.sensors.store(uuid.UUID(sensors.gid))

        return TimeSeriesEEG(), ts_idx, ts_h5

    ts_builder = {TS_REGION: create_region_ts, TS_EEG: create_eeg_ts}

    @transactional
    def launch(self, data_file, dataset_name, structure_path='',
               transpose=False, slice=None, sampling_rate=1000,
               start_time=0, tstype_parameters=None):
        try:
            data = read_nested_mat_file(data_file, dataset_name, structure_path)

            if transpose:
                data = data.T
            if slice:
                data = data[parse_slice(slice)]

            ts, ts_idx, ts_h5 = self.ts_builder[self.tstype](self, data.shape, tstype_parameters)

            ts.start_time = start_time
            ts.sample_period_unit = 's'

            ts_h5.write_time_slice(numpy.r_[:data.shape[0]] * ts.sample_period)
            # we expect empirical data shape to be time, channel.
            # But tvb expects time, state, channel, mode. Introduce those dimensions
            ts_h5.write_data_slice(data[:, numpy.newaxis, :, numpy.newaxis])

            data_shape = ts_h5.read_data_shape()
            ts_h5.nr_dimensions.store(len(data_shape))
            ts_h5.gid.store(uuid.UUID(ts_idx.gid))
            ts_h5.sample_period.store(ts.sample_period)
            ts_h5.sample_period_unit.store(ts.sample_period_unit)
            ts_h5.sample_rate.store(ts.sample_rate)
            ts_h5.start_time.store(ts.start_time)
            ts_h5.labels_ordering.store(ts.labels_ordering)
            ts_h5.labels_dimensions.store(ts.labels_dimensions)
            ts_h5.title.store(ts.title)
            ts_h5.close()

            ts_idx.title = ts.title
            ts_idx.time_series_type = type(ts).__name__
            ts_idx.sample_period_unit = ts.sample_period_unit
            ts_idx.sample_period = ts.sample_period
            ts_idx.sample_rate = ts.sample_rate
            ts_idx.labels_dimensions = json.dumps(ts.labels_dimensions)
            ts_idx.labels_ordering = json.dumps(ts.labels_ordering)
            ts_idx.data_ndim = len(data_shape)
            ts_idx.data_length_1d, ts_idx.data_length_2d, ts_idx.data_length_3d, ts_idx.data_length_4d = prepare_array_shape_meta(
                data_shape)

            return ts_idx
        except ParseException as ex:
            self.log.exception(ex)
            raise LaunchException(ex)
