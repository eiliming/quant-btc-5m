from __future__ import annotations

import unittest

from src.core.pipeline import DatasetBuildConfig, FeatureBuildConfig, ResearchBuildConfig, ResearchPipeline


class PipelineTests(unittest.TestCase):
    def test_pipeline_exposes_research_os_lifecycle_methods(self) -> None:
        pipeline = ResearchPipeline()

        self.assertTrue(callable(pipeline.build_dataset))
        self.assertTrue(callable(pipeline.run_qa))
        self.assertTrue(callable(pipeline.build_research))
        self.assertTrue(callable(pipeline.build_feature))
        self.assertEqual(DatasetBuildConfig.__name__, "DatasetBuildConfig")
        self.assertEqual(ResearchBuildConfig.__name__, "ResearchBuildConfig")
        self.assertEqual(FeatureBuildConfig.__name__, "FeatureBuildConfig")


if __name__ == "__main__":
    unittest.main()
