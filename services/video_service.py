import os
import tempfile
import requests
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, concatenate_videoclips
import google.generativeai as genai
from pydub import AudioSegment
import base64

class VideoGenerator:
    def __init__(self, gemini_api_key):
        self.gemini_api_key = gemini_api_key
        genai.configure(api_key=gemini_api_key)
    
    def generate_travel_video(self, script, itinerary, style="Cinematic", duration=60):
        """Generate travel video using available resources"""
        try:
            # Create temporary directory for assets
            with tempfile.TemporaryDirectory() as temp_dir:
                # Parse script into scenes
                scenes = self._parse_script_to_scenes(script)
                
                # Generate or retrieve video clips for each scene
                video_clips = []
                
                for i, scene in enumerate(scenes):
                    # For demo purposes, we'll use stock videos or create simple animations
                    # In production, you would integrate with Veo3 or other video generation APIs
                    scene_clip = self._create_scene_clip(scene, i, temp_dir)
                    if scene_clip:
                        video_clips.append(scene_clip)
                
                if not video_clips:
                    # Create a simple slideshow as fallback
                    video_clips = self._create_fallback_video(itinerary, temp_dir)
                
                # Combine all clips
                final_video = concatenate_videoclips(video_clips)
                
                # Generate narration
                narration_audio = self._generate_narration(script, temp_dir)
                if narration_audio:
                    final_video = final_video.set_audio(narration_audio)
                
                # Add background music
                final_video = self._add_background_music(final_video, temp_dir)
                
                # Export final video
                output_path = os.path.join(temp_dir, "final_travel_story.mp4")
                final_video.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True
                )
                
                return output_path
                
        except Exception as e:
            print(f"Video generation error: {str(e)}")
            return None
    
    def _parse_script_to_scenes(self, script):
        """Parse the script into individual scenes"""
        scenes = []
        current_scene = {}
        
        for line in script.split('\n'):
            line = line.strip()
            if line.startswith('[SCENE'):
                if current_scene:
                    scenes.append(current_scene)
                current_scene = {'number': len(scenes) + 1}
            elif line.startswith('VISUAL:'):
                current_scene['visual'] = line.replace('VISUAL:', '').strip()
            elif line.startswith('NARRATION:'):
                current_scene['narration'] = line.replace('NARRATION:', '').strip().strip('"')
        
        if current_scene:
            scenes.append(current_scene)
        
        return scenes if scenes else [{'visual': 'Beautiful travel scenery', 'narration': 'Welcome to your journey!'}]
    
    def _create_scene_clip(self, scene, index, temp_dir):
        """Create a video clip for a scene"""
        try:
            # For demo: Create simple text-based video clips
            # In production, replace with actual video generation using Veo3
            
            # Create a simple text clip as placeholder
            clip = TextClip(
                txt=scene['visual'],
                fontsize=24,
                color='white',
                size=(640, 480),
                bg_color='black'
            ).set_duration(5)  # 5 seconds per scene
            
            return clip
            
        except Exception as e:
            print(f"Scene creation error: {str(e)}")
            return None
    
    def _create_fallback_video(self, itinerary, temp_dir):
        """Create fallback video when no scenes are available"""
        clips = []
        
        # Create title clip
        title_clip = TextClip(
            txt=f"Journey from {itinerary['from']} to {itinerary['to']}",
            fontsize=30,
            color='yellow',
            size=(640, 480),
            bg_color='blue'
        ).set_duration(5)
        clips.append(title_clip)
        
        # Create clips for each POI
        for i, poi in enumerate(itinerary.get('points_of_interest', [])[:5]):
            if isinstance(poi, dict):
                poi_name = poi.get('name', f'Location {i+1}')
                clip = TextClip(
                    txt=poi_name,
                    fontsize=24,
                    color='white',
                    size=(640, 480),
                    bg_color='green'
                ).set_duration(4)
                clips.append(clip)
        
        return clips
    
    def _generate_narration(self, script, temp_dir):
        """Generate narration audio using TTS"""
        try:
            # Extract narration text from script
            narration_lines = []
            for line in script.split('\n'):
                if line.startswith('NARRATION:'):
                    narration_text = line.replace('NARRATION:', '').strip().strip('"')
                    narration_lines.append(narration_text)
            
            if not narration_lines:
                narration_lines = ["Welcome to your travel adventure!"]
            
            full_narration = " ".join(narration_lines)
            
            # For demo: Use gTTS or other TTS service
            # In production, use Google Cloud Text-to-Speech or similar
            from gtts import gTTS
            
            audio_path = os.path.join(temp_dir, "narration.mp3")
            tts = gTTS(text=full_narration[:500], lang='en', slow=False)  # Limit text length
            tts.save(audio_path)
            
            return AudioFileClip(audio_path)
            
        except Exception as e:
            print(f"Narration generation error: {str(e)}")
            return None
    
    def _add_background_music(self, video_clip, temp_dir):
        """Add background music to video"""
        try:
            # For demo: Download royalty-free music or use simple audio
            # In production, use proper royalty-free music library
            
            # Placeholder - return original video without music
            return video_clip
            
        except Exception as e:
            print(f"Background music error: {str(e)}")
            return video_clip
