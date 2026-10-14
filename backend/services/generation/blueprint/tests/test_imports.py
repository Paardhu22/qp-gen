import sys
import os

# Try to import things to ensure no circular or missing dependencies
try:
    from services.generation.blueprint.subjects.science import science
    from services.generation.blueprint.orchestration import choreography, pipeline, psychology
    from services.generation.blueprint.retrieval import semantic_index
    from services.generation.blueprint.compiler import blueprint_compiler, safety_engine
    from services.generation.blueprint.master.facade import AcademicGenerationFacade
    print("SUCCESS: All imports resolved correctly.")
except Exception as e:
    print(f"FAILURE: Import failed. {e}")
    sys.exit(1)
