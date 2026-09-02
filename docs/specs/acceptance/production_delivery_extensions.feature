Feature: Production delivery extensions
  Scenario: Director refinement is rate limited without changing models
    Given an OpenAI-compatible Director endpoint returns HTTP 429
    When the endpoint supplies a Retry-After delay
    Then MelosViz retries after that delay with the configured model
    And deterministic template prompts remain available if retries fail

  Scenario: Every completed clip has review evidence
    Given a scene render completes
    When MelosViz writes clip provenance
    Then the record contains artifact and prompt hashes
    And a deterministic SVG timeline thumbnail exists

  Scenario: Festival delivery includes portable cues
    Given a rendered master and storyboard metadata
    When the operator runs viz ship
    Then final.zip contains the media manifest
    And final.zip contains one SVG and one Lottie cue per discovered shot

  Scenario: Offline GPU smoke remains honest
    Given no physical GPU backend is connected
    When the weekly GPU smoke workflow runs in offline mode
    Then it verifies deterministic artifact topology
    And it does not claim physical GPU rendering succeeded
