# Copyright 2021 IBM All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""These testcases consider the case where the input bundle has more than one resource and NLP overrides"""
# pylint: disable=missing-function-docstring
import importlib

from fhir.resources.bundle import Bundle
from fhir.resources.diagnosticreport import DiagnosticReport

from nlp_insights import app
from test_nlp_insights.util import enrich_text
from test_nlp_insights.util import unstructured_text
from test_nlp_insights.util.compare import compare_actual_to_expected
from test_nlp_insights.util.fhir import (
    make_diag_report,
    make_attachment,
    make_bundle,
    make_patient_reference,
    make_codeable_concept,
    make_patient,
    make_allergy_intolerance,
    make_condition,
)
from test_nlp_insights.util.mock_service import (
    make_mock_acd_service_class,
    configure_acd,
    make_mock_quick_umls_service_class,
    configure_quick_umls,
    configure_resource_nlp_override,
)
from test_nlp_insights.util.resources import UnitTestUsingExternalResource


class TestEnrichWithMultipleNLP(UnitTestUsingExternalResource):
    """Tests what happens when a resource is enriched by both of our NLP engines"""

    def setUp(self) -> None:
        # The application is defined globally in the module, so this is a potentially
        # flawed way of reseting the state between test cases.
        # It should work "well-enough" in most cases.
        importlib.reload(app)
        app.all_nlp_services["acd"] = make_mock_acd_service_class(
            [
                str(self.resource_path) + "/acd/TestReportResponses.json",
                str(self.resource_path) + "/acd/TestEnrichResponses.json",
            ]
        )
        app.all_nlp_services["quickumls"] = make_mock_quick_umls_service_class(
            [
                str(self.resource_path) + "/quickUmls/TestReportResponses.json",
                str(self.resource_path) + "/quickUmls/TestEnrichResponses.json",
            ]
        )

    def test_when_enrich_with_quickumls_and_acd_then_all_insights(self):
        bundle = make_bundle(
            [
                make_condition(
                    subject=make_patient_reference(),
                    code=make_codeable_concept(text=enrich_text.CONDITION_HEART_ATTACK),
                )
            ]
        )

        with app.app.test_client() as service:
            configure_quick_umls(service)
            insight_resp = service.post("/discoverInsights", json=bundle.dict())
            self.assertEqual(200, insight_resp.status_code)

            first_bundle = Bundle.parse_obj(insight_resp.get_json())
            self.assertTrue(len(first_bundle.entry) == 1)
            qumls_enriched_condition = first_bundle.entry[0].resource

            configure_acd(service)

            new_bundle = make_bundle([qumls_enriched_condition])
            insight_resp = service.post("/discoverInsights", data=new_bundle.json())
            self.assertEqual(200, insight_resp.status_code)

            actual_bundle = Bundle.parse_obj(insight_resp.get_json())
            cmp = compare_actual_to_expected(
                expected_path=self.expected_output_path(),
                actual_resource=actual_bundle,
            )
            self.assertFalse(cmp, cmp.pretty())

    def test_when_enrich_with_acd_and_quickumls_then_all_insights(self):
        bundle = make_bundle(
            [
                make_condition(
                    subject=make_patient_reference(),
                    code=make_codeable_concept(text=enrich_text.CONDITION_HEART_ATTACK),
                )
            ]
        )

        with app.app.test_client() as service:
            configure_acd(service)
            insight_resp = service.post("/discoverInsights", json=bundle.dict())
            self.assertEqual(200, insight_resp.status_code)

            first_bundle = Bundle.parse_obj(insight_resp.get_json())
            self.assertTrue(len(first_bundle.entry) == 1)
            qumls_enriched_condition = first_bundle.entry[0].resource

            configure_quick_umls(service)
            new_bundle = make_bundle([qumls_enriched_condition])
            insight_resp = service.post("/discoverInsights", data=new_bundle.json())
            self.assertEqual(200, insight_resp.status_code)

            actual_bundle = Bundle.parse_obj(insight_resp.get_json())
            cmp = compare_actual_to_expected(
                expected_path=self.expected_output_path(),
                actual_resource=actual_bundle,
            )
            self.assertFalse(cmp, cmp.pretty())


class TestMultiResourceBundleWithOverride(UnitTestUsingExternalResource):
    """Unit tests where a bundle has multiple resources"""

    def setUp(self) -> None:
        # The application is defined globally in the module, so this is a potentially
        # flawed way of reseting the state between test cases.
        # It should work "well-enough" in most cases.
        importlib.reload(app)
        app.all_nlp_services["acd"] = make_mock_acd_service_class(
            [
                str(self.resource_path) + "/acd/TestReportResponses.json",
                str(self.resource_path) + "/acd/TestEnrichResponses.json",
            ]
        )
        app.all_nlp_services["quickumls"] = make_mock_quick_umls_service_class(
            [
                str(self.resource_path) + "/quickUmls/TestReportResponses.json",
                str(self.resource_path) + "/quickUmls/TestEnrichResponses.json",
            ]
        )

    def test_when_qu_override_diag_report_then_correct_bundle_is_returned(self):
        bundle = make_bundle(
            [
                make_diag_report(
                    subject=make_patient_reference(),
                    attachments=[
                        make_attachment(
                            unstructured_text.TEXT_FOR_CONDITION_AND_MEDICATION
                        )
                    ],
                ),
                make_allergy_intolerance(
                    patient=make_patient_reference(),
                    code=make_codeable_concept(text=enrich_text.ALLERGY_PEANUT),
                ),
                # Patient is here to prove that resources that we don't know how to handle
                # will not cause a problem
                make_patient(),
            ]
        )

        with app.app.test_client() as service:
            configure_acd(service)
            cfg_qu = configure_quick_umls(service, is_default=False)
            configure_resource_nlp_override(service, DiagnosticReport, cfg_qu)
            insight_resp = service.post("/discoverInsights", data=bundle.json())
            self.assertEqual(200, insight_resp.status_code)

            actual_bundle = Bundle.parse_obj(insight_resp.get_json())
            cmp = compare_actual_to_expected(
                expected_path=self.expected_output_path(),
                actual_resource=actual_bundle,
            )
            self.assertFalse(cmp, cmp.pretty())

    def test_when_acd_override_diag_report_then_correct_bundle_is_returned(self):
        bundle = make_bundle(
            [
                make_diag_report(
                    subject=make_patient_reference(),
                    attachments=[
                        make_attachment(
                            unstructured_text.TEXT_FOR_CONDITION_AND_MEDICATION
                        )
                    ],
                ),
                make_allergy_intolerance(
                    patient=make_patient_reference(),
                    code=make_codeable_concept(text=enrich_text.ALLERGY_PEANUT),
                ),
                # Patient is here to prove that resources that we don't know how to handle
                # will not cause a problem
                make_patient(),
            ]
        )

        with app.app.test_client() as service:
            configure_quick_umls(service)
            cfg_acd = configure_acd(service, is_default=False)
            configure_resource_nlp_override(service, DiagnosticReport, cfg_acd)
            insight_resp = service.post("/discoverInsights", data=bundle.json())
            self.assertEqual(200, insight_resp.status_code)

            actual_bundle = Bundle.parse_obj(insight_resp.get_json())
            cmp = compare_actual_to_expected(
                expected_path=self.expected_output_path(),
                actual_resource=actual_bundle,
            )
            self.assertFalse(cmp, cmp.pretty())
