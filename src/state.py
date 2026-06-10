from typing import TypedDict, Optional, Any


class RefactoringState(TypedDict):
    # Input
    instruction: Optional[str]
    repository_path: str

    # Planner output
    file_plans: list[dict[str, Any]]

    # Validator input
    validation_tests: list[str]

    # RefactoringAgent output, dict since we need to differentiate between the refactored code of different files
    refactored_code: dict[str, str]

    # CompilerAgent output
    compile_error: Optional[str]
    compile_attempts: int

    # TesterAgent output
    test_error: Optional[str]
    test_attempts: int

    # Test generation metrics
    tests_generated: int
    test_coverage: float

    # Final
    success: bool