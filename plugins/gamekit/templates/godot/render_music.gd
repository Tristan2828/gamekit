extends SceneTree
## Renders the game's own music to WAV files for gamekit (`gamekit music render`).
## Copy to tools/render_music.gd, then set in assets.yaml:
##   music:
##     godot_project: .
##     render_script: tools/render_music.gd
## gamekit runs:
##   Godot --headless --path . -s tools/render_music.gd -- --out=<folder> --track=<name> ...
## and expects <folder>/<name>.wav for every --track. Scripts run with -s don't get autoloads,
## so use plain classes (class_name scripts) to make the music.


func _init() -> void:
	var out_dir := "."
	var tracks: Array[String] = []
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--out="):
			out_dir = arg.trim_prefix("--out=")
		elif arg.begins_with("--track="):
			tracks.append(arg.trim_prefix("--track="))
	DirAccess.make_dir_recursive_absolute(out_dir)
	for track: String in tracks:
		var stream := render(track)
		if stream == null:
			push_error("Unknown track %s" % track)
			quit(1)
			return
		var path := out_dir.path_join("%s.wav" % track)
		if stream.save_to_wav(path) != OK:
			push_error("Can't write %s" % path)
			quit(1)
			return
		print("rendered %s -> %s" % [track, path])
	quit()


## TODO: return the track as an AudioStreamWAV (16-bit), e.g. from your synth or composer:
##   var stream := AudioStreamWAV.new()
##   stream.format = AudioStreamWAV.FORMAT_16_BITS
##   stream.mix_rate = 44100
##   stream.data = <PackedByteArray of 16-bit samples>
## Return null for a name you don't know.
func render(_track: String) -> AudioStreamWAV:
	return null
