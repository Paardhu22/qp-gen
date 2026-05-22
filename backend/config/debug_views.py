import time
import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def science_engine_health(request):
    start_time = time.time()
    logger.info("Starting science engine health check...")
    try:
        # Import validation
        import_start = time.time()
        from q_instructions.master.facade import AcademicGenerationFacade, GeneratePaperRequest
        from q_instructions.core.enums import EducationBoard, AcademicClass, ExamType
        import_time = (time.time() - import_start) * 1000
        logger.info(f"Engine import success in {import_time:.2f}ms")
        
        # Initialization
        init_start = time.time()
        facade = AcademicGenerationFacade()
        init_time = (time.time() - init_start) * 1000
        logger.info(f"Engine initialization timing: {init_time:.2f}ms")

        # Dry run generation
        gen_start = time.time()
        paper_req = GeneratePaperRequest(
            board="CBSE",
            academic_class="CLASS_10",
            exam_type="FINAL",
            chapters=["Electricity"],
            difficulty="medium",
            institution_id="DPS_E_DELHI",
            seed=101
        )
        res = facade.generate_paper(paper_req)
        gen_time = (time.time() - gen_start) * 1000
        logger.info(f"Dry-run generation timing: {gen_time:.2f}ms. Generated {len(res.questions)} questions.")
        
        return Response({
            "status": "ok",
            "imports": "ok",
            "engine": "reachable",
            "metrics": {
                "import_time_ms": round(import_time, 2),
                "init_time_ms": round(init_time, 2),
                "gen_time_ms": round(gen_time, 2),
                "total_time_ms": round((time.time() - start_time) * 1000, 2)
            }
        })
    except Exception as e:
        logger.error(f"Package resolution or engine failure: {e}", exc_info=True)
        return Response({
            "status": "error",
            "imports": "failed",
            "engine": "unreachable",
            "error": str(e)
        }, status=500)
