import os
import shutil
import subprocess
import json
from pathlib import Path

from check_framenum import get_video_meta
from movdata_forcopy import check_and_fix_permissions



def save_mov_frame(folder_path: Path, output_txt_path: Path):
    """
    Extract frame count of .mov files in a folder and save to a txt file.
    """
    video_extension = ['.mov']
    with open(output_txt_path, 'w', encoding='utf-8') as f_out:
        for filename in os.listdir(folder_path):
            if filename.startswith("._"):
                continue
            if any(filename.lower().endswith(ext) for ext in video_extension):
                file_path = folder_path / filename
                check_and_fix_permissions(file_path)
                try:
                    meta = get_video_meta(file_path, entries="stream=r_frame_rate,nb_frames,codec_name:format=duration")
                    if not meta or 'nb_frames' not in meta:
                        print(f"[SKIP] Unsupported file or unreadable metadata: {file_path}")
                        continue
                    n_frame = meta['nb_frames']
                    f_out.write(f"{file_path} : {n_frame}\n")
                    print(f"{file_path} : {n_frame}")
                except Exception as e:
                    print(f"[ERROR] Failed to extract metadata from {file_path}: {e}")
                    
def extract_frames(txt_path: Path):
    """
    Extract frames from video files listed in a txt file.
    - Copies videos to tmp directory
    - Saves frames to frames_<txt_name>/<framecount>_<videoname> folder
    - Saves source.txt with metadata
    - Cleans up tmp folder after processing
    """
    output_root = txt_path.parent / f"frames_{txt_path.stem}"
    output_root.mkdir(parents=True, exist_ok=True)

    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        if ':' not in line:
            continue

        video_path_str, _ = line.strip().split(':')
        video_path = Path(video_path_str.strip())
        video_name = video_path.stem

        tmp_dir = video_path.parent / "tmp"
        tmp_dir.mkdir(exist_ok=True)

        temp_video_path = tmp_dir / video_path.name

        try:
            shutil.copy2(video_path, temp_video_path)

            metadata = get_video_meta(temp_video_path, entries="stream=r_frame_rate,nb_frames,codec_name:format=duration")
            if not metadata or "nb_frames" not in metadata:
                print(f"[SKIP] Missing metadata or nb_frames: {video_path}")
                continue

            frame_count = int(metadata["nb_frames"])
            frame_dir_name = f"{frame_count}_{video_name}"
            frame_dir = output_root / frame_dir_name
            frame_dir.mkdir(parents=True, exist_ok=True)

            with open(frame_dir / "source.txt", 'w', encoding='utf-8') as f_src:
                f_src.write(f"[Original Path]\n{video_path.resolve()}\n\n")
                f_src.write("[Metadata]\n")
                f_src.write(json.dumps(metadata, indent=2, ensure_ascii=False))

            ffmpeg_cmd = [
                "ffmpeg", "-i", str(temp_video_path),
                "-pix_fmt", "rgb48",
                str(frame_dir / "%08d.tiff")
            ]
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"[EXTRACTED] Frames saved to: {frame_dir}")

        except Exception as e:
            print(f"[ERROR] Failed processing {video_path}: {e}")

        finally:
            if temp_video_path.exists():
                temp_video_path.unlink()
            try:
                tmp_dir.rmdir()
            except OSError:
                print(f"[CLEANUP] Could not remove tmp folder: {tmp_dir}")

def organize_frame_folders(frames_root: Path):
    """
    Organize extracted TIFF frames into subfolders based on frame count rules.
    Original TIFF files will be deleted after sorting.
    """
    assert frames_root.exists(), f"[ERROR] Path does not exist: {frames_root}"

    for folder in frames_root.iterdir():
        if not folder.is_dir():
            continue

        source_file = folder / "source.txt"
        if not source_file.exists():
            print(f"[SKIP] No source.txt in {folder.name}")
            continue

        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                content = f.read()
                meta_json = content.split("[Metadata]")[-1].strip()
                meta = json.loads(meta_json)
                total_frames = int(meta.get("nb_frames", 0))
        except Exception as e:
            print(f"[ERROR] Failed parsing metadata in {folder.name}: {e}")
            continue

        frame_files = sorted(folder.glob("*.tiff"))
        total_available = len(frame_files)

        if total_available < 5 or total_frames <= 5:
            shutil.rmtree(folder)
            print(f"[REMOVED] {folder.name} - only {total_available} frames")
            continue

        folder_index = 1

        def move_frames(indices):
            nonlocal folder_index
            subfolder = folder / f"{folder_index:03d}"
            subfolder.mkdir(exist_ok=True)
            for idx in indices:
                if 0 <= idx < total_available:
                    src = frame_files[idx]
                    dst = subfolder / src.name
                    shutil.move(str(src), str(dst))
            folder_index += 1

        # Frame selection rules based on total frame count:
        if 6 <= total_frames <= 9:      # 6–9 frames: skip the first frame, use next 5 frames
            move_frames(range(1, 6))

        elif 10 <= total_frames <= 19:      # 10–19 frames: use all frames in a single folder
            move_frames(range(0, total_available))

        elif 20 <= total_frames <= 24:      # 20–24 frames: use the first 20 frames only
            move_frames(range(0, 20))

        elif 25 <= total_frames <= 249:        # 25–249 frames: skip first 5 frames, use next 20 frames
            move_frames(range(5, 25))

        elif 250 <= total_frames <= 599:        # 250–599 frames:
        # - Front: skip first 5 frames, use frames 5–25 (20 frames)
        # - Rear: skip last 5 frames, use frames from -26 to -6 (20 frames)
            move_frames(range(5, 26))
            move_frames(range(total_available - 26, total_available - 5))

        elif total_frames >= 600:       # 600+ frames:
            # - Exclude first 5 frames
            # - Select 5 sets of 20 frames at equal intervals (every 146 frames)
            # - Fixed starting points: [5, 151, 297, 443, 589]
            for start in enumerate([5, 151, 297, 443, 589]):
                end = start + 20
                move_frames(range(start, end))

        else:
            # No matching condition for frame count
            print(f"[SKIP] {folder.name} - No matching rule")

        for tiff in folder.glob("*.tiff"):
            tiff.unlink()

        print(f"[DONE] {folder.name} - {total_frames} frames sorted")



if __name__ == "__main__":
    
    input_dir = Path("/mnt/d/CBFT01-02/video/(Video)ca&be_ep1-2/6.편집/복사_ep01-02/")
    txt_path = Path("./test0716.txt")

    # # Step 1: Save frame metadata to txt
    save_mov_frame(input_dir, txt_path)

    # # Step 2: Extract frames from video list
    extract_frames(txt_path)

    # Step 3: Organize extracted frames
    organize_frame_folders(txt_path.parent / f"frames_{txt_path.stem}")
    
    
    
# import subprocess
# import json
# from pathlib import Path
# from fractions import Fraction
# from decimal import Decimal, getcontext
# from typing import Optional

# def get_video_meta(file_path: Path, entries: str = "stream=r_frame_rate,duration,nb_frames", *, lock=None) -> Optional[dict]:
#     """비디오 메타데이터를 가져오는 함수"""
#     def _get_video_meta(file_path: Path) -> Optional[dict]:
#         try:
#             probe = subprocess.run(
#                 [
#                     "ffprobe", "-v", "warning",
#                     "-select_streams", "v:0",
#                     "-show_entries", entries,
#                     "-of", "json=c=1", 
#                     file_path
#                 ],
#                 text=True, capture_output=True, check=True
#             )
#             probe_json = json.loads(probe.stdout)
#             keys = [e.split('=')[0] for e in entries.split(':')]
            
#             meta = {}
#             for key in keys:
#                 source = probe_json[key + "s"][0] if key == "stream" else probe_json[key]
#                 meta.update(source)

#             if file_path.suffix.lower() == ".mkv" and "nb_frames" in entries:
#                 from fractions import Fraction
#                 from decimal import Decimal, getcontext
                
#                 # getcontext().prec = 28
#                 fps = Fraction(meta["r_frame_rate"])
#                 duration = Decimal(meta["duration"])
                
#                 fps_decimal = Decimal(fps.numerator) / Decimal(fps.denominator)
#                 nb_frames = int(round(fps_decimal * duration))
                
#                 meta["nb_frames"] = str(nb_frames)

#             return meta
#         except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
#             print(f"Error probing {file_path}: {e}")
#             return None
        
#     if lock is None:
#         return _get_video_meta(file_path)
#     else:
#         with lock:
#             return _get_video_meta(file_path)
        
# meta = get_video_meta(Path("/home/inshorts/sowoojoo_0529.mkv"), entries="stream=r_frame_rate,nb_frames,codec_name:format=duration")
# print(meta)import os
import shutil
import subprocess
import json
from pathlib import Path

from check_framenum import get_video_meta
from movdata_forcopy import check_and_fix_permissions



def save_mov_frame(folder_path: Path, output_txt_path: Path):
    """
    Extract frame count of .mov files in a folder and save to a txt file.
    """
    video_extension = ['.mov']
    with open(output_txt_path, 'w', encoding='utf-8') as f_out:
        for filename in os.listdir(folder_path):
            if filename.startswith("._"):
                continue
            if any(filename.lower().endswith(ext) for ext in video_extension):
                file_path = folder_path / filename
                check_and_fix_permissions(file_path)
                try:
                    meta = get_video_meta(file_path, entries="stream=r_frame_rate,nb_frames,codec_name:format=duration")
                    if not meta or 'nb_frames' not in meta:
                        print(f"[SKIP] Unsupported file or unreadable metadata: {file_path}")
                        continue
                    n_frame = meta['nb_frames']
                    f_out.write(f"{file_path} : {n_frame}\n")
                    print(f"{file_path} : {n_frame}")
                except Exception as e:
                    print(f"[ERROR] Failed to extract metadata from {file_path}: {e}")
                    
def extract_frames(txt_path: Path):
    """
    Extract frames from video files listed in a txt file.
    - Copies videos to tmp directory
    - Saves frames to frames_<txt_name>/<framecount>_<videoname> folder
    - Saves source.txt with metadata
    - Cleans up tmp folder after processing
    """
    output_root = txt_path.parent / f"frames_{txt_path.stem}"
    output_root.mkdir(parents=True, exist_ok=True)

    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line in lines:
        if ':' not in line:
            continue

        video_path_str, _ = line.strip().split(':')
        video_path = Path(video_path_str.strip())
        video_name = video_path.stem

        tmp_dir = video_path.parent / "tmp"
        tmp_dir.mkdir(exist_ok=True)

        temp_video_path = tmp_dir / video_path.name

        try:
            shutil.copy2(video_path, temp_video_path)

            metadata = get_video_meta(temp_video_path, entries="stream=r_frame_rate,nb_frames,codec_name:format=duration")
            if not metadata or "nb_frames" not in metadata:
                print(f"[SKIP] Missing metadata or nb_frames: {video_path}")
                continue

            frame_count = int(metadata["nb_frames"])
            frame_dir_name = f"{frame_count}_{video_name}"
            frame_dir = output_root / frame_dir_name
            frame_dir.mkdir(parents=True, exist_ok=True)

            with open(frame_dir / "source.txt", 'w', encoding='utf-8') as f_src:
                f_src.write(f"[Original Path]\n{video_path.resolve()}\n\n")
                f_src.write("[Metadata]\n")
                f_src.write(json.dumps(metadata, indent=2, ensure_ascii=False))

            ffmpeg_cmd = [
                "ffmpeg", "-i", str(temp_video_path),
                "-pix_fmt", "rgb48",
                str(frame_dir / "%08d.tiff")
            ]
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"[EXTRACTED] Frames saved to: {frame_dir}")

        except Exception as e:
            print(f"[ERROR] Failed processing {video_path}: {e}")

        finally:
            if temp_video_path.exists():
                temp_video_path.unlink()
            try:
                tmp_dir.rmdir()
            except OSError:
                print(f"[CLEANUP] Could not remove tmp folder: {tmp_dir}")

def organize_frame_folders(frames_root: Path):
    """
    Organize extracted TIFF frames into subfolders based on frame count rules.
    Original TIFF files will be deleted after sorting.
    """
    assert frames_root.exists(), f"[ERROR] Path does not exist: {frames_root}"

    for folder in frames_root.iterdir():
        if not folder.is_dir():
            continue

        source_file = folder / "source.txt"
        if not source_file.exists():
            print(f"[SKIP] No source.txt in {folder.name}")
            continue

        try:
            with open(source_file, 'r', encoding='utf-8') as f:
                content = f.read()
                meta_json = content.split("[Metadata]")[-1].strip()
                meta = json.loads(meta_json)
                total_frames = int(meta.get("nb_frames", 0))
        except Exception as e:
            print(f"[ERROR] Failed parsing metadata in {folder.name}: {e}")
            continue

        frame_files = sorted(folder.glob("*.tiff"))
        total_available = len(frame_files)

        if total_available < 5 or total_frames <= 5:
            shutil.rmtree(folder)
            print(f"[REMOVED] {folder.name} - only {total_available} frames")
            continue

        folder_index = 1

        def move_frames(indices):
            nonlocal folder_index
            subfolder = folder / f"{folder_index:03d}"
            subfolder.mkdir(exist_ok=True)
            for idx in indices:
                if 0 <= idx < total_available:
                    src = frame_files[idx]
                    dst = subfolder / src.name
                    shutil.move(str(src), str(dst))
            folder_index += 1

        # Frame selection rules based on total frame count:
        if 6 <= total_frames <= 9:      # 6–9 frames: skip the first frame, use next 5 frames
            move_frames(range(1, 6))

        elif 10 <= total_frames <= 19:      # 10–19 frames: use all frames in a single folder
            move_frames(range(0, total_available))

        elif 20 <= total_frames <= 24:      # 20–24 frames: use the first 20 frames only
            move_frames(range(0, 20))

        elif 25 <= total_frames <= 249:        # 25–249 frames: skip first 5 frames, use next 20 frames
            move_frames(range(5, 25))

        elif 250 <= total_frames <= 599:        # 250–599 frames:
        # - Front: skip first 5 frames, use frames 5–25 (20 frames)
        # - Rear: skip last 5 frames, use frames from -26 to -6 (20 frames)
            move_frames(range(5, 26))
            move_frames(range(total_available - 26, total_available - 5))

        elif total_frames >= 600:       # 600+ frames:
            # - Exclude first 5 frames
            # - Select 5 sets of 20 frames at equal intervals (every 146 frames)
            # - Fixed starting points: [5, 151, 297, 443, 589]
            for start in enumerate([5, 151, 297, 443, 589]):
                end = start + 20
                move_frames(range(start, end))

        else:
            # No matching condition for frame count
            print(f"[SKIP] {folder.name} - No matching rule")

        for tiff in folder.glob("*.tiff"):
            tiff.unlink()

        print(f"[DONE] {folder.name} - {total_frames} frames sorted")



if __name__ == "__main__":
    
    input_dir = Path("/mnt/d/CBFT01-02/video/(Video)ca&be_ep1-2/6.편집/복사_ep01-02/")
    txt_path = Path("./test0716.txt")

    # # Step 1: Save frame metadata to txt
    save_mov_frame(input_dir, txt_path)

    # # Step 2: Extract frames from video list
    extract_frames(txt_path)

    # Step 3: Organize extracted frames
    organize_frame_folders(txt_path.parent / f"frames_{txt_path.stem}")
    
    
    
# import subprocess
# import json
# from pathlib import Path
# from fractions import Fraction
# from decimal import Decimal, getcontext
# from typing import Optional

# def get_video_meta(file_path: Path, entries: str = "stream=r_frame_rate,duration,nb_frames", *, lock=None) -> Optional[dict]:
#     """비디오 메타데이터를 가져오는 함수"""
#     def _get_video_meta(file_path: Path) -> Optional[dict]:
#         try:
#             probe = subprocess.run(
#                 [
#                     "ffprobe", "-v", "warning",
#                     "-select_streams", "v:0",
#                     "-show_entries", entries,
#                     "-of", "json=c=1", 
#                     file_path
#                 ],
#                 text=True, capture_output=True, check=True
#             )
#             probe_json = json.loads(probe.stdout)
#             keys = [e.split('=')[0] for e in entries.split(':')]
            
#             meta = {}
#             for key in keys:
#                 source = probe_json[key + "s"][0] if key == "stream" else probe_json[key]
#                 meta.update(source)

#             if file_path.suffix.lower() == ".mkv" and "nb_frames" in entries:
#                 from fractions import Fraction
#                 from decimal import Decimal, getcontext
                
#                 # getcontext().prec = 28
#                 fps = Fraction(meta["r_frame_rate"])
#                 duration = Decimal(meta["duration"])
                
#                 fps_decimal = Decimal(fps.numerator) / Decimal(fps.denominator)
#                 nb_frames = int(round(fps_decimal * duration))
                
#                 meta["nb_frames"] = str(nb_frames)

#             return meta
#         except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
#             print(f"Error probing {file_path}: {e}")
#             return None
        
#     if lock is None:
#         return _get_video_meta(file_path)
#     else:
#         with lock:
#             return _get_video_meta(file_path)
        
# meta = get_video_meta(Path("/home/inshorts/sowoojoo_0529.mkv"), entries="stream=r_frame_rate,nb_frames,codec_name:format=duration")
# print(meta)
