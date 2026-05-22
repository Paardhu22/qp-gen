import sys
import os

# Try to import things to ensure no circular or missing dependencies
try:
    from q_instructions.subjects.science import science
    from q_instructions.orchestration import choreography, pipeline, psychology
    from q_instructions.retrieval import semantic_index
    from q_instructions.generation import blueprint_compiler, safety_engine
    from q_instructions.master.facade import AcademicGenerationFacade
    print("SUCCESS: All imports resolved correctly.")
except Exception as e:
    print(f"FAILURE: Import failed. {e}")
    sys.exit(1)
