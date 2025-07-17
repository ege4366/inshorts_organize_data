import subprocess
import os
import sys
from pathlib import Path
import argparse

def trim_video_with_copy(input_path, output_path, start_time, end_time):
    """
    ffmpeg을 사용해서 비디오의 특정 구간을 copy 코덱으로 자르는 함수
    Args:
        input_path (str): 입력 비디오 파일 경로
        output_path (str): 출력 비디오 파일 경로
        start_time (str): 시작 시간 (HH:MM:SS 또는 초 단위)
        end_time (str): 종료 시간 (HH:MM:SS 또는 초 단위)
    Returns:
        bool: 성공 여부
    """
    try:
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-to', str(end_time),
            '-i', input_path,
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-y',
            output_path
        ]
        print(f"실행 명령어: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 비디오 자르기 성공!")
            print(f"입력 파일: {input_path}")
            print(f"출력 파일: {output_path}")
            print(f"구간: {start_time} ~ {end_time}")
            return True
        else:
            print(f"❌ 비디오 자르기 실패!")
            print(f"에러: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌오류 발생: {str(e)}")
        return False

def format_time(seconds):
    """
    초 단위를 HH:MM:SS 형식으로 변환
    Args:
        seconds (float): 초 단위 시간
    Returns:
        str: HH:MM:SS 형식의 시간
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

def main():
    parser = argparse.ArgumentParser(
        description="ffmpeg로 비디오의 특정 구간을 copy 모드로 자르는 도구",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input', help='입력 비디오 파일 경로')
    parser.add_argument('output', nargs='?', help='출력 비디오 파일 경로 (생략 시 자동 생성)', default=None)
    parser.add_argument('--start', required=True, help='시작 시간 (초 단위 또는 HH:MM:SS)')
    parser.add_argument('--end', required=True, help='종료 시간 (초 단위 또는 HH:MM:SS)')
    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"❌ 파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        output_path = f"trimmed_{Path(input_path).name}"

    start_input = args.start
    end_input = args.end

    print("\n🔄 비디오 자르기 시작...")
    success = trim_video_with_copy(input_path, output_path, start_input, end_input)
    if success:
        print("\n🎉 작업이 완료되었습니다!")
    else:
        print("\n💥 작업이 실패했습니다.")

if __name__ == "__main__":
    main() 