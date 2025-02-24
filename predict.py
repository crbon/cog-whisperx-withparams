# Prediction interface for Cog ⚙️
# https://github.com/replicate/cog/blob/main/docs/python.md
import os
os.environ['HF_HOME'] = '/src/hf_models'
os.environ['TORCH_HOME'] = '/src/torch_models'
from cog import BasePredictor, Input, Path
import torch
import whisperx
import faster_whisper
import json


compute_type="float16"
class Predictor(BasePredictor):
    def setup(self):
        """Load the model into memory to make running multiple predictions efficient"""
        self.device = "cuda"
        self.model = whisperx.load_model("large-v2", self.device, language="en", compute_type=compute_type)
        self.alignment_model, self.metadata = whisperx.load_align_model(language_code="en", device=self.device)

    def predict(
        self,
        audio: Path = Input(description="Audio file"),
        batch_size: int = Input(description="Parallelization of input audio transcription", default=32),
        align_output: bool = Input(description="Use if you need word-level timing and not just batched transcription", default=False),
        initial_prompt: str = Input(description="Optional text to provide as a prompt for the first window.", default=""),
        debug: bool = Input(description="Print out memory usage information.", default=False)
    ) -> str:
        """Run a single prediction on the model"""
        with torch.inference_mode():
            if initial_prompt:
                new_asr_options = self.model.options._asdict()
                new_asr_options["initial_prompt"] = "Your new initial prompt"
                new_options = faster_whisper.transcribe.TranscriptionOptions(**new_asr_options)
                self.model.options = new_options
            result = self.model.transcribe(str(audio), batch_size=batch_size)
            # result is dict w/keys ['segments', 'language']
            # segments is a list of dicts,each dict has {'text': <text>, 'start': <start_time_msec>, 'end': <end_time_msec> }
            if align_output:
                # NOTE - the "only_text" flag makes no sense with this flag, but we'll do it anyway
                result = whisperx.align(result['segments'], self.alignment_model, self.metadata, str(audio), self.device, return_char_alignments=False)
                # dict w/keys ['segments', 'word_segments']
                # aligned_result['word_segments'] = list[dict], each dict contains {'word': <word>, 'start': <start_time_msec>, 'end': <end_time_msec>, 'score': probability}
                #   it is also sorted
                # aligned_result['segments'] - same as result segments, but w/a ['words'] segment which contains timing information above.
                # return_char_alignments adds in character level alignments. it is: too many.
            if debug:
                print(f"max gpu memory allocated over runtime: {torch.cuda.max_memory_reserved() / (1024 ** 3):.2f} GB")

        # Flush GPU memory after each inference
        torch.cuda.empty_cache()
        
        return json.dumps(result['segments'])
