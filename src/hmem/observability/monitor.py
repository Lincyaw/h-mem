"""Memory quality monitoring with golden dataset.

Implements observability from design.md:
- Golden dataset regression testing
- Recall/precision measurement
- Quality degradation detection
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
import json
import structlog

logger = structlog.get_logger()


class RetrievalProtocol(Protocol):
    """Protocol for retrieval callable."""

    def __call__(self, query: str, top_k: int = 10) -> list[str]:
        """Retrieve memory IDs for query."""
        ...


@dataclass
class GoldenTestCase:
    """A single golden test case."""

    query: str
    expected_ids: list[str]
    min_recall: float = 0.8
    created_at: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    """Result of running a single test case."""

    query: str
    expected_ids: list[str]
    retrieved_ids: list[str]
    recall: float
    precision: float
    passed: bool
    duration_ms: float


@dataclass
class RegressionReport:
    """Full regression test report."""

    run_at: datetime
    total_cases: int
    passed_cases: int
    failed_cases: int
    avg_recall: float
    min_recall: float
    avg_precision: float
    results: list[TestResult]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "run_at": self.run_at.isoformat(),
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "avg_recall": self.avg_recall,
            "min_recall": self.min_recall,
            "avg_precision": self.avg_precision,
        }


class MemoryQualityMonitor:
    """Monitors retrieval quality using golden dataset.

    Runs regression tests to ensure code changes don't degrade recall.

    Golden dataset format (JSON):
    ```json
    {
      "test_cases": [
        {
          "query": "web scraping tips",
          "expected_ids": ["evt_123", "evt_456"],
          "min_recall": 0.8
        }
      ]
    }
    ```

    Example:
        >>> monitor = MemoryQualityMonitor(golden_path="./tests/golden.json")
        >>> report = monitor.run_regression(retriever_fn)
        >>> assert report.avg_recall >= 0.85
    """

    def __init__(self, golden_path: Path | str) -> None:
        """Initialize quality monitor.

        Args:
            golden_path: Path to golden dataset JSON
        """
        self.golden_path = Path(golden_path)
        self._test_cases: list[GoldenTestCase] = []
        self._load_golden_dataset()

    def _load_golden_dataset(self) -> None:
        """Load golden dataset from file."""
        if not self.golden_path.exists():
            logger.debug("golden_dataset_not_found", path=str(self.golden_path))
            return

        try:
            with open(self.golden_path) as f:
                data = json.load(f)

            for case_data in data.get("test_cases", []):
                case = GoldenTestCase(
                    query=case_data["query"],
                    expected_ids=case_data["expected_ids"],
                    min_recall=case_data.get("min_recall", 0.8),
                    tags=case_data.get("tags", []),
                )
                self._test_cases.append(case)

            logger.info(
                "golden_dataset_loaded",
                path=str(self.golden_path),
                count=len(self._test_cases),
            )
        except Exception as e:
            logger.error("golden_dataset_load_failed", error=str(e))

    def _save_golden_dataset(self) -> None:
        """Save golden dataset to file."""
        data = {
            "test_cases": [
                {
                    "query": case.query,
                    "expected_ids": case.expected_ids,
                    "min_recall": case.min_recall,
                    "tags": case.tags,
                }
                for case in self._test_cases
            ]
        }

        self.golden_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.golden_path, "w") as f:
            json.dump(data, f, indent=2)

    def run_regression(
        self,
        retriever: RetrievalProtocol,
        top_k: int = 10,
    ) -> RegressionReport:
        """Run golden dataset tests.

        Args:
            retriever: Function that takes query and returns list of memory IDs
            top_k: Number of results to retrieve

        Returns:
            RegressionReport with results
        """
        import time

        results: list[TestResult] = []

        for case in self._test_cases:
            start = time.perf_counter()
            retrieved = retriever(case.query, top_k=top_k)
            duration_ms = (time.perf_counter() - start) * 1000

            # Calculate recall and precision
            expected_set = set(case.expected_ids)
            retrieved_set = set(retrieved)

            if expected_set:
                recall = len(expected_set & retrieved_set) / len(expected_set)
            else:
                recall = 1.0 if not retrieved_set else 0.0

            if retrieved_set:
                precision = len(expected_set & retrieved_set) / len(retrieved_set)
            else:
                precision = 1.0 if not expected_set else 0.0

            passed = recall >= case.min_recall

            result = TestResult(
                query=case.query,
                expected_ids=case.expected_ids,
                retrieved_ids=retrieved,
                recall=recall,
                precision=precision,
                passed=passed,
                duration_ms=duration_ms,
            )
            results.append(result)

        # Aggregate stats
        total = len(results)
        passed_count = sum(1 for r in results if r.passed)
        recalls = [r.recall for r in results]
        precisions = [r.precision for r in results]

        report = RegressionReport(
            run_at=datetime.now(),
            total_cases=total,
            passed_cases=passed_count,
            failed_cases=total - passed_count,
            avg_recall=sum(recalls) / total if total else 0.0,
            min_recall=min(recalls) if recalls else 0.0,
            avg_precision=sum(precisions) / total if total else 0.0,
            results=results,
        )

        logger.info(
            "regression_completed",
            total=report.total_cases,
            passed=report.passed_cases,
            avg_recall=f"{report.avg_recall:.2%}",
        )

        return report

    def add_golden_case(
        self,
        query: str,
        expected_ids: list[str],
        min_recall: float = 0.8,
        tags: list[str] | None = None,
    ) -> None:
        """Add test case to golden dataset.

        Args:
            query: Test query
            expected_ids: Expected memory IDs
            min_recall: Minimum required recall
            tags: Optional tags for filtering
        """
        case = GoldenTestCase(
            query=query,
            expected_ids=expected_ids,
            min_recall=min_recall,
            tags=tags or [],
        )
        self._test_cases.append(case)
        self._save_golden_dataset()

        logger.info(
            "golden_case_added",
            query=query,
            expected_count=len(expected_ids),
        )

    def remove_golden_case(self, query: str) -> bool:
        """Remove test case by query.

        Args:
            query: Query to remove

        Returns:
            True if removed
        """
        original_len = len(self._test_cases)
        self._test_cases = [c for c in self._test_cases if c.query != query]

        if len(self._test_cases) < original_len:
            self._save_golden_dataset()
            return True
        return False

    def get_cases_by_tag(self, tag: str) -> list[GoldenTestCase]:
        """Get test cases with specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of matching test cases
        """
        return [c for c in self._test_cases if tag in c.tags]

    def get_stats(self) -> dict[str, Any]:
        """Get monitor statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_cases": len(self._test_cases),
            "golden_path": str(self.golden_path),
            "exists": self.golden_path.exists(),
        }
