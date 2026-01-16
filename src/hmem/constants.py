"""Centralized configuration constants for the hmem system."""

# Consolidator constants
CONSOLIDATOR_MAX_WORKERS = 2
CONSOLIDATOR_MAX_RETRIES = 3
CONSOLIDATOR_TIMEOUT = 30.0
CONSOLIDATOR_RETRY_DELAY = 1.0
CONSOLIDATOR_FORGETTING_THRESHOLD = 0.3
CONSOLIDATOR_DECAY_FACTOR = 0.99
CONSOLIDATOR_REFINEMENT_MIN_USAGE = 10
CONSOLIDATOR_REFINEMENT_MIN_SUCCESS_RATE = 0.5

# Memory system constants
MEMORY_SYSTEM_TIMEOUT = 30.0
MEMORY_SYSTEM_MAX_WORKERS = 4

# Ranking constants
# Updated to match interfaces.md HybridRankerWithExploration
RANKING_DEFAULT_SIMILARITY_WEIGHT = 0.5  # Primary signal
RANKING_DEFAULT_RECENCY_WEIGHT = 0.15
RANKING_DEFAULT_IMPORTANCE_WEIGHT = 0.15
RANKING_DEFAULT_OUTCOME_WEIGHT = 0.2  # Kept for backward compatibility
RANKING_DEFAULT_QUALITY_WEIGHT = 0.2  # Quality score from IndexProfile
RANKING_DEFAULT_EXPLORATION_WEIGHT = 0.1  # Exploration bonus for low-usage memories
RANKING_DEFAULT_IMPORTANCE_NORMALIZER = 100.0
RANKING_DEFAULT_RECENCY_HALFLIFE_DAYS = 30.0
RANKING_DEFAULT_SUCCESS_BOOST = 1.0
RANKING_DEFAULT_FAILURE_PENALTY = 0.3
RANKING_DEFAULT_INITIAL_EXPLORATION_RATE = 0.2
RANKING_DEFAULT_MIN_EXPLORATION_RATE = 0.05

# Embedding constants
EMBEDDING_DEFAULT_DIMENSION = 384
EMBEDDING_WORD_SCALE_FACTOR = 0.1

# Database constants
NEO4J_MAX_CONNECTION_RETRIES = 3
NEO4J_CONNECTION_RETRY_DELAY = 1.0

# Skill matching constants
SKILL_EXACT_MATCH_SCORE = 1.0
SKILL_SUBSTRING_MATCH_SCORE = 0.8
SKILL_DEFAULT_MATCH_THRESHOLD = 0.6

# Q-Learning constants (MemRL-inspired)
# Learning rate for Q-value updates (0.1 = smooth, 0.3 = fast adaptation)
Q_LEARNING_DEFAULT_ALPHA = 0.1

# QValueRanker weights (must sum to 1.0)
Q_LEARNING_DEFAULT_SIMILARITY_WEIGHT = 0.5  # Semantic relevance
Q_LEARNING_DEFAULT_Q_WEIGHT = 0.35  # Learned utility
Q_LEARNING_DEFAULT_FRESHNESS_WEIGHT = 0.15  # Information timeliness

# Freshness decay half-life in days
Q_LEARNING_DEFAULT_FRESHNESS_HALFLIFE_DAYS = 30.0

# Q-value thresholds for refinement triggers
Q_LEARNING_REFINE_Q_THRESHOLD_LOW = 0.3  # Q below this + high usage = refine
Q_LEARNING_REFINE_MIN_USAGE = 5  # Minimum updates before considering refine
Q_LEARNING_DEPRECATE_Q_THRESHOLD = 0.2  # Q below this = deprecation candidate
Q_LEARNING_DEPRECATE_MIN_USAGE = 10  # Minimum updates for deprecation

# Q-value inheritance on refine
Q_LEARNING_INHERITANCE_Q_DECAY = 0.8  # Inherit 80% of old Q-value
Q_LEARNING_INHERITANCE_CONFIDENCE_DECAY = 0.5  # Inherit 50% of update count

# Default Q-value for new memories
Q_LEARNING_DEFAULT_Q_VALUE = 0.5  # Neutral starting point

# Confidence calculation: full confidence at this many updates
Q_LEARNING_FULL_CONFIDENCE_UPDATES = 20

# Type-specific freshness weights (Gemini feedback fix)
# Principle (L3 wisdom) should not decay with time - truth is timeless
# Skill (L2 procedural) decays slowly - procedures may become outdated
# Semantic (L2 facts) decays moderately - facts may change
# Episodic (L1 events) decays fully - recent events are more relevant
TYPE_FRESHNESS_WEIGHTS: dict[str, float] = {
    "episodic": 1.0,  # Full freshness weight
    "semantic": 0.7,  # Reduced freshness weight
    "skill": 0.3,  # Low freshness weight
    "principle": 0.0,  # No freshness decay for wisdom
}

# Refined reward mapping (Gemini feedback fix)
# Distinguishes between "recalled and used" vs "recalled but ignored"
REWARD_SUCCESS = 1.0  # Memory was used and led to success
REWARD_FAILURE = 0.0  # Memory was used and led to failure
REWARD_UNKNOWN_USED = 0.6  # Memory was used but outcome unknown (slight positive)
REWARD_UNKNOWN_IGNORED = 0.4  # Memory was recalled but ignored (slight negative)
