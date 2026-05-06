"""
Prometheus metrics for Phase 7 monitoring.

Tracks:
- Queries answered by the Query Agent
- Capability gaps detected
- Tasks created
- Tools deployed
- Test pass/fail rates
- Deployment times
"""
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry

# Create a registry for all metrics
REGISTRY = CollectorRegistry()

# ──────────────────────────────────────────────────────────────────────────────
# Counters (ever-increasing)
# ──────────────────────────────────────────────────────────────────────────────

queries_answered = Counter(
    "agent_queries_answered_total",
    "Total number of queries answered by the Query Agent",
    registry=REGISTRY,
)

capability_gaps_detected = Counter(
    "agent_capability_gaps_total",
    "Total number of capability gaps detected",
    registry=REGISTRY,
)

tasks_created = Counter(
    "agent_tasks_created_total",
    "Total number of tasks created from capability gaps",
    registry=REGISTRY,
)

tasks_approved = Counter(
    "agent_tasks_approved_total",
    "Total number of tasks approved for development",
    registry=REGISTRY,
)

tasks_deployed = Counter(
    "agent_tasks_deployed_total",
    "Total number of tasks deployed successfully",
    registry=REGISTRY,
)

tasks_escalated = Counter(
    "agent_tasks_escalated_total",
    "Total number of tasks escalated (agent failed)",
    registry=REGISTRY,
)

tools_deployed = Counter(
    "agent_tools_deployed_total",
    "Total number of tools deployed",
    registry=REGISTRY,
)

tools_rolled_back = Counter(
    "agent_tools_rolled_back_total",
    "Total number of tools rolled back",
    registry=REGISTRY,
)

tests_passed = Counter(
    "agent_tests_passed_total",
    "Total number of tests that passed",
    registry=REGISTRY,
)

tests_failed = Counter(
    "agent_tests_failed_total",
    "Total number of tests that failed",
    registry=REGISTRY,
)

# ──────────────────────────────────────────────────────────────────────────────
# Gauges (can go up or down)
# ──────────────────────────────────────────────────────────────────────────────

tasks_pending = Gauge(
    "agent_tasks_pending",
    "Number of tasks pending approval",
    registry=REGISTRY,
)

tasks_in_development = Gauge(
    "agent_tasks_in_development",
    "Number of tasks currently in development",
    registry=REGISTRY,
)

available_tools = Gauge(
    "agent_available_tools",
    "Number of available tools in the registry",
    registry=REGISTRY,
)

# ──────────────────────────────────────────────────────────────────────────────
# Histograms (distribution of values)
# ──────────────────────────────────────────────────────────────────────────────

query_response_time = Histogram(
    "agent_query_response_seconds",
    "Time taken to respond to a query (in seconds)",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=REGISTRY,
)

code_generation_time = Histogram(
    "agent_code_generation_seconds",
    "Time taken to generate code (in seconds)",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
    registry=REGISTRY,
)

test_execution_time = Histogram(
    "agent_test_execution_seconds",
    "Time taken to execute tests (in seconds)",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

deployment_time = Histogram(
    "agent_deployment_seconds",
    "Time taken to deploy a tool (in seconds)",
    buckets=(1.0, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

code_coverage_percent = Gauge(
    "agent_code_coverage_percent",
    "Code coverage percentage for generated tools",
    registry=REGISTRY,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions for incrementing metrics
# ──────────────────────────────────────────────────────────────────────────────

def increment_queries_answered():
    """Increment the queries answered counter."""
    queries_answered.inc()


def increment_capability_gaps_detected():
    """Increment the capability gaps detected counter."""
    capability_gaps_detected.inc()


def increment_tasks_created():
    """Increment the tasks created counter."""
    tasks_created.inc()


def increment_tasks_approved():
    """Increment the tasks approved counter."""
    tasks_approved.inc()


def increment_tasks_deployed():
    """Increment the tasks deployed counter."""
    tasks_deployed.inc()


def increment_tasks_escalated():
    """Increment the tasks escalated counter."""
    tasks_escalated.inc()


def increment_tools_deployed():
    """Increment the tools deployed counter."""
    tools_deployed.inc()


def increment_tools_rolled_back():
    """Increment the tools rolled back counter."""
    tools_rolled_back.inc()


def increment_tests_passed():
    """Increment the tests passed counter."""
    tests_passed.inc()


def increment_tests_failed():
    """Increment the tests failed counter."""
    tests_failed.inc()


def set_tasks_pending(count: int):
    """Set the number of pending tasks."""
    tasks_pending.set(count)


def set_tasks_in_development(count: int):
    """Set the number of tasks in development."""
    tasks_in_development.set(count)


def set_available_tools(count: int):
    """Set the number of available tools."""
    available_tools.set(count)


def set_code_coverage(percent: float):
    """Set the code coverage percentage."""
    code_coverage_percent.set(percent)
