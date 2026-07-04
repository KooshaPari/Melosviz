Feature: Self-Diagnose Script (`make diagnose`)
  As a developer or operator onboarding to MelosViz
  I want a single command that reports PASS/FAIL on environment prerequisites
  So that I can quickly verify ffmpeg, Python version, and optional tools are available

  Background:
    Given a fresh Python 3.10+ interpreter is on PATH
    And the diagnose script module is importable as `scripts.diagnose`
    And the `run_diagnose()` function returns a `DiagnoseReport`

  # FR-50 #1
  Scenario: All required checks pass
    Given ffmpeg is resolvable on PATH or via MELOSVIZ_FFMPEG_BIN
    And Python version is at least 3.10
    When I invoke `run_diagnose()`
    Then every required check has status PASS
    And the report's `required_passed` is True
    And the report's `exit_code` is 0

  # FR-50 #1
  Scenario: Missing ffmpeg fails the script with non-zero exit
    Given ffmpeg is NOT resolvable on PATH
    And MELOSVIZ_FFMPEG_BIN is unset or points to a missing binary
    When I invoke `run_diagnose()`
    Then the ffmpeg check has status FAIL
    And the report's `required_passed` is False
    And the report's `exit_code` is 1

  # FR-50 #2
  Scenario: Optional adapter (blender) absent produces WARN not FAIL
    Given the optional `bpy` module is not importable
    When I invoke `run_diagnose()`
    Then the blender check has status WARN
    And the report's `exit_code` is 0
    And the report's `required_passed` is True

  # FR-50 #2
  Scenario: All optional adapters absent all produce WARN
    Given the optional modules `bpy`, `demucs`, `librosa` are not importable
    And no `wgpu` adapter is enumerable
    When I invoke `run_diagnose()`
    Then the blender, demucs, librosa, and gpu-wgpu checks all have status WARN
    And the report's `exit_code` is 0

  # FR-50 #3
  Scenario: Output table has Check / Status / Detail columns
    When I render the diagnose output table
    Then the header row contains the columns "Check", "Status", and "Detail"
    And every body row has exactly three columns aligned with the header
    And the status column is one of "PASS", "WARN", or "FAIL"

  # FR-50 #4
  Scenario: Exit code 0 on all-pass, 1 on required-fail
    Given a diagnose run where all required checks pass
    When I inspect the report's `exit_code`
    Then it equals 0
    Given a diagnose run where at least one required check fails
    When I inspect the report's `exit_code`
    Then it equals 1

  # FR-50 #5
  Scenario: DiagnoseReport exposes checks, required_passed, and exit_code
    When I invoke `run_diagnose()`
    Then the report has an attribute `checks` that is a list
    And every element of `checks` has attributes `name`, `status`, and `detail`
    And the report has an attribute `required_passed` that is a bool
    And the report has an attribute `exit_code` that is an int
