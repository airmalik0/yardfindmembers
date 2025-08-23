from typing import Dict, Any, List, Optional, TypedDict
import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agents.image_analyzer import ImageAnalyzerAgent
from agents.text_analyzer import TextAnalyzerAgent
from agents.embedding_agent import EmbeddingAgent
from utils.data_models import WorkflowState, MemberProfile, AnalysisRequest
import config
from pathlib import Path


class ProfileWorkflowState(TypedDict):
    """State for the profile processing workflow"""
    image_path: Optional[str]
    raw_text: Optional[str]
    profile: Optional[Dict[str, Any]]
    analysis_request: Optional[Dict[str, Any]]
    analysis_result: Optional[Dict[str, Any]]
    error: Optional[str]
    was_cached: Optional[bool]  # Флаг, показывающий что профиль был загружен из кэша


class ProfileProcessingWorkflow:
    """Main workflow for processing YARD Business Club profiles"""
    
    def __init__(self):
        self.image_analyzer = ImageAnalyzerAgent()
        self.text_analyzer = TextAnalyzerAgent()
        self.workflow = self._build_workflow()
        
    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow"""
        
        # Create workflow
        workflow = StateGraph(ProfileWorkflowState)
        
        # Add nodes
        workflow.add_node("analyze_image", self._analyze_image_node)
        workflow.add_node("analyze_text", self._analyze_text_node)
        
        # Define the flow
        workflow.set_entry_point("analyze_image")
        
        # Add conditional edge from analyze_image
        workflow.add_conditional_edges(
            "analyze_image",
            self._should_analyze_text,
            {
                "analyze": "analyze_text",
                "end": END
            }
        )
        
        # End after text analysis
        workflow.add_edge("analyze_text", END)
        
        return workflow.compile()
    
    def _analyze_image_node(self, state: ProfileWorkflowState) -> ProfileWorkflowState:
        """Node for image analysis"""
        result = self.image_analyzer(state)
        return result
    
    def _analyze_text_node(self, state: ProfileWorkflowState) -> ProfileWorkflowState:
        """Node for text analysis"""
        result = self.text_analyzer(state)
        return result
    
    def _should_analyze_text(self, state: ProfileWorkflowState) -> str:
        """Decide whether to proceed with text analysis"""
        if state.get("error"):
            return "end"
        if state.get("analysis_request") and state.get("profile"):
            return "analyze"
        return "end"
    
    def process_single_image(self, image_path: str, analysis_request: Optional[AnalysisRequest] = None) -> Dict[str, Any]:
        """Process a single image"""
        initial_state = {
            "image_path": image_path,
            "analysis_request": analysis_request.model_dump() if analysis_request else None
        }
        
        result = self.workflow.invoke(initial_state)
        return result
    
    def process_batch_images(self, image_paths: List[str]) -> List[Dict[str, Any]]:
        """Process multiple images"""
        results = []
        
        for image_path in image_paths:
            print(f"\nProcessing: {image_path}", flush=True)
            try:
                result = self.process_single_image(image_path)
                results.append(result)
                
                if result.get("error"):
                    print(f"  Error: {result['error']}", flush=True)
                else:
                    profile = result.get("profile")
                    if profile:
                        # Проверяем, был ли профиль загружен из кэша или создан заново
                        if result.get("was_cached"):
                            print(f"  ✓ Using existing profile for: {profile.get('name', 'Unknown')}", flush=True)
                            print(f"  ✓ Already indexed in embeddings", flush=True)
                        else:
                            print(f"  ✓ Extracted profile for: {profile.get('name', 'Unknown')}", flush=True)
                            
                            # Index profile for embedding search only for new profiles
                            try:
                                embedding_agent = EmbeddingAgent()
                                profile_obj = MemberProfile(**profile)
                                embedding_agent.index_profile(profile_obj)
                                print(f"  ✓ Indexed for embedding search", flush=True)
                            except Exception as e:
                                print(f"  ⚠ Could not index for embeddings: {str(e)}", flush=True)
            except Exception as e:
                print(f"  ✗ Failed to process: {str(e)}", flush=True)
                results.append({"image_path": image_path, "error": str(e)})
        
        return results
    
    def analyze_all_profiles(self, criteria: str) -> List[Dict[str, Any]]:
        """Analyze all saved profiles against criteria"""
        analyzer = TextAnalyzerAgent()
        results = analyzer.batch_analyze(criteria)
        
        # Return matching profiles
        matching_profiles = []
        for result in results:
            if result.matches:
                # Load full profile
                profile_path = config.PROFILES_DIR / f"{result.profile_name.replace(' ', '_')}.json"
                if profile_path.exists():
                    with open(profile_path, 'r', encoding='utf-8') as f:
                        profile_data = json.load(f)
                        matching_profiles.append({
                            "profile": profile_data,
                            "analysis": result.model_dump()
                        })
        
        return matching_profiles


class BatchProcessingWorkflow:
    """Workflow for batch processing of images"""
    
    def __init__(self):
        self.profile_workflow = ProfileProcessingWorkflow()
    
    def discover_images(self, directory: Path = None) -> List[str]:
        """Discover all images in the specified directory"""
        if directory is None:
            directory = config.PHOTOS_DIR
        
        image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(directory.glob(f"*{ext}"))
            image_files.extend(directory.glob(f"*{ext.upper()}"))
        
        # Filter out thumbnails
        image_files = [f for f in image_files if 'thumb' not in f.name.lower()]
        
        return [str(f) for f in image_files]
    
    def process_all_images(self, directory: Path = None) -> Dict[str, Any]:
        """Process all images in directory"""
        image_paths = self.discover_images(directory)
        
        if not image_paths:
            print(f"No images found in {directory or config.PHOTOS_DIR}", flush=True)
            return {"error": "No images found", "processed": 0}
        
        print(f"Found {len(image_paths)} images to process", flush=True)
        
        results = self.profile_workflow.process_batch_images(image_paths)
        
        # Summary
        successful = sum(1 for r in results if not r.get("error"))
        failed = len(results) - successful
        
        summary = {
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": results
        }
        
        print(f"\n{'='*50}", flush=True)
        print(f"Processing complete:", flush=True)
        print(f"  Total: {summary['total']}", flush=True)
        print(f"  Successful: {summary['successful']}", flush=True)
        print(f"  Failed: {summary['failed']}", flush=True)
        
        return summary