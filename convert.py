from moviepy import VideoFileClip

def extract(video_path, audio_name, audio_format):
	"""
	Function that extract audio from video
	Assintotic: O(1)
	"""
	video = VideoFileClip(video_path)
	audio = video.audio
	audio.write_audiofile(audio_name + '.' + audio_format)

try:
	extract(video, audio_name, audio_format)

except Exception as e: print(e)



if __name__ == "__main__":
    video = "How to Add an Emergency Contact.webm"
    audio_format = "mp3"
    audio_name = "emergency_contact_audio"
    extract(video_path=video, audio_name=audio_name, audio_format=audio_format)