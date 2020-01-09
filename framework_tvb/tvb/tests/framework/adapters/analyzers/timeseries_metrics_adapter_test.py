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
.. moduleauthor:: bogdan.neacsa <bogdan.neacsa@codemart.ro>
"""

import os
import tvb_data
import json
from tvb.adapters.datatypes.db.mapped_value import DatatypeMeasureIndex
from tvb.core.neocom import h5
from tvb.tests.framework.core.base_testcase import TransactionalTestCase
from tvb.config.init.introspector_registry import IntrospectionRegistry
from tvb.core.entities.model import model_operation
from tvb.core.entities.storage import dao
from tvb.core.entities.file.files_helper import FilesHelper
from tvb.adapters.analyzers.metrics_group_timeseries import TimeseriesMetricsAdapter, TimeseriesMetricsAdapterForm
from tvb.core.entities.transient.structure_entities import DataTypeMetaData
from tvb.core.services.flow_service import FlowService
from tvb.tests.framework.core.factory import TestFactory


class TestTimeSeriesMetricsAdapter(TransactionalTestCase):
    """
    Test the timeseries metric adapter.
    """

    def transactional_setup_method(self):
        """
        Sets up the environment for running the tests;
        creates a test user and a test project, saves old configuration and imports a CFF data-set
        """
        self.test_user = TestFactory.create_user()
        self.test_project = TestFactory.create_project(self.test_user)
        zip_path = os.path.join(os.path.dirname(tvb_data.__file__), 'connectivity', 'connectivity_66.zip')
        TestFactory.import_zip_connectivity(self.test_user, self.test_project, zip_path);

    def transactional_teardown_method(self):
        """
        Remove project folders and clean up database.
        """
        FilesHelper().remove_project_structure(self.test_project.name)

    def test_adapter_launch(self, connectivity_factory, region_mapping_factory, time_series_region_index_factory):
        """
        Test that the adapters launches and successfully generates a datatype measure entry.
        """
        meta = {DataTypeMetaData.KEY_SUBJECT: "John Doe", DataTypeMetaData.KEY_STATE: "RAW_DATA"}
        algo = FlowService().get_algorithm_by_module_and_class(IntrospectionRegistry.SIMULATOR_MODULE,
                                                               IntrospectionRegistry.SIMULATOR_CLASS)
        self.operation = model_operation.Operation(self.test_user.id, self.test_project.id, algo.id, json.dumps(''),
                                         meta=json.dumps(meta), status=model_operation.STATUS_STARTED)
        self.operation = dao.store_entity(self.operation)

        # Get connectivity, region_mapping and a dummy time_series_region
        connectivity = connectivity_factory()
        region_mapping = region_mapping_factory()
        dummy_time_series_index = time_series_region_index_factory(connectivity=connectivity, region_mapping=region_mapping)

        dummy_time_series_index.start_time = 0.0
        dummy_time_series_index.sample_period = 1.0

        dummy_time_series_index = dao.get_generic_entity(dummy_time_series_index.__class__, dummy_time_series_index.gid, 'gid')[0]
        dummy_time_series = h5.load_from_index(dummy_time_series_index)
        ts_metric_adapter = TimeseriesMetricsAdapter()
        form = TimeseriesMetricsAdapterForm()
        view_model = form.get_view_model()()
        view_model.time_series = dummy_time_series.gid
        form.fill_trait(view_model)
        ts_metric_adapter.submit_form(form)
        resulted_metric = ts_metric_adapter.launch(view_model)
        assert isinstance(resulted_metric, DatatypeMeasureIndex), "Result should be a datatype measure."
        assert len(resulted_metric.metrics) >= len(list(ts_metric_adapter.get_form().algorithms.choices)),\
                        "At least a result should have been generated for every metric."
        for metric_value in json.loads(resulted_metric.metrics).values():
            assert isinstance(metric_value, (float, int))
