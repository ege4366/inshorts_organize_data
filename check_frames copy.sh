#!/bin/bash

# 영상 파일 경로 (명령행 인수로 받거나 기본값 사용)
VIDEO_FILE="${1:-sowoojoo_0529_compressed.mov}"

echo "=== 영상 프레임 정보 확인 ==="
echo "파일: $VIDEO_FILE"
echo ""

# 기본 프레임 정보
echo "1. 기본 프레임 정보:"
ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=nb_frames,r_frame_rate,duration \
        -of csv=p=0 "$VIDEO_FILE" | \
while IFS=',' read -r fps duration frames; do
    echo "   총 프레임 수: $frames"
    echo "   프레임 레이트: $fps fps"
    echo "   재생 시간: $duration 초"
    
    # fps를 계산
    fps_num=$(echo $fps | cut -d'/' -f1)
    fps_den=$(echo $fps | cut -d'/' -f2)
    fps_calc=$(echo "scale=2; $fps_num / $fps_den" | bc)
    echo "   계산된 FPS: $fps_calc"
    
    # 시간당 프레임 수 계산 (duration이 유효한 경우에만)
    if [[ "$duration" != "N/A" && "$duration" != "" && "$duration" != "0" ]]; then
        frames_per_second=$(echo "scale=2; $frames / $duration" | bc 2>/dev/null || echo "계산 불가")
        echo "   초당 평균 프레임: $frames_per_second"
    fi
done

# duration이나 frames가 N/A인 경우 대안적인 방법 사용
echo ""
echo "2. 대안적 프레임 정보 (duration/frames가 N/A인 경우):"
DURATION_ALT=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO_FILE")
FRAMES_ALT=$(ffprobe -v quiet -select_streams v:0 -count_frames -show_entries stream=nb_read_frames -of csv=p=0 "$VIDEO_FILE")

if [[ "$DURATION_ALT" != "N/A" && "$DURATION_ALT" != "" ]]; then
    echo "   재생 시간 (format): $DURATION_ALT 초"
    
    # FPS 정보 가져오기
    FPS_INFO=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO_FILE")
    if [[ "$FPS_INFO" != "" ]]; then
        fps_num=$(echo $FPS_INFO | cut -d'/' -f1)
        fps_den=$(echo $FPS_INFO | cut -d'/' -f2)
        fps_calc=$(echo "scale=2; $fps_num / $fps_den" | bc 2>/dev/null || echo "계산 불가")
        echo "   FPS: $fps_calc"
        
        # 예상 프레임 수 계산
        # expected_frames=$(echo "scale=0; $DURATION_ALT * $fps_calc / 1" | bc 2>/dev/null || echo "계산 불가")
        #echo "   예상 총 프레임 수: $expected_frames"
    fi
fi

if [[ "$FRAMES_ALT" != "N/A" && "$FRAMES_ALT" != "" ]]; then
    echo "   읽은 프레임 수: $FRAMES_ALT"
fi

echo ""
echo "3. 상세 정보:"
# jq가 없는 경우를 대비한 대안
if command -v jq &> /dev/null; then
    ffprobe -v quiet -print_format json \
            -show_streams -select_streams v:0 "$VIDEO_FILE" | \
    jq -r '.streams[0] | "   해상도: \(.width) x \(.height)\n   코덱: \(.codec_name)\n   비트레이트: \(.bit_rate) bps"'
else
    echo "   jq가 설치되지 않았습니다. 기본 정보만 표시합니다:"
    ffprobe -v quiet -select_streams v:0 \
            -show_entries stream=width,height,codec_name,bit_rate \
            -of csv=p=0 "$VIDEO_FILE" | \
    while IFS=',' read -r width height codec bitrate; do
        echo "   해상도: ${width}x${height}"
        echo "   코덱: $codec"
        echo "   비트레이트: $bitrate bps"
    done
fi

echo ""
echo "4. 키 프레임 정보:"
echo "   키 프레임 개수 확인 중..."
# 더 빠른 방법으로 키 프레임 개수 확인
KEYFRAME_COUNT=$(ffprobe -v quiet -select_streams v:0 \
                 -show_entries frame=pict_type \
                 -of csv=p=0 "$VIDEO_FILE" 2>/dev/null | grep -c "I" || echo "0")
echo "   키 프레임 개수: $KEYFRAME_COUNT"

# 키 프레임 인덱스 정보 추가
echo ""
echo "5. 키 프레임 인덱스 상세 정보:"
echo "   키 프레임 인덱스와 시간 정보 확인 중..."

# FPS 정보 가져오기
FPS_CALC=$(ffprobe -v quiet -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO_FILE" | \
           while IFS=',' read -r fps; do
               fps_num=$(echo $fps | cut -d'/' -f1)
               fps_den=$(echo $fps | cut -d'/' -f2)
               echo "scale=2; $fps_num / $fps_den" | bc 2>/dev/null || echo "30"
           done)

# 키 프레임 인덱스와 시간 정보 추출
echo "   키 프레임 목록 (프레임 번호 - 시간):"
KEYFRAME_INFO=$(ffprobe -v quiet -select_streams v:0 \
                -show_entries frame=pict_type,pts_time \
                -of csv=p=0 "$VIDEO_FILE" 2>/dev/null | \
                awk -F',' '$2 == "I" {print $1}' | head -20)

if [[ -n "$KEYFRAME_INFO" ]]; then
    frame_count=0
    echo "$KEYFRAME_INFO" | while read -r pts_time; do
        if [[ -n "$pts_time" && "$pts_time" != "N/A" ]]; then
            frame_count=$((frame_count + 1))
            # 프레임 번호 계산 (시간 * FPS)
            frame_number=$(echo "scale=0; $pts_time * $FPS_CALC / 1" | bc 2>/dev/null || echo "계산 불가")
            echo "   키프레임 $frame_count: 프레임 $frame_number (시간: ${pts_time}초)"
        fi
    done
    
    # 전체 키프레임 개수가 20개보다 많으면 안내
    TOTAL_KEYFRAMES=$(echo "$KEYFRAME_INFO" | wc -l)
    if [[ $TOTAL_KEYFRAMES -ge 20 ]]; then
        echo "   ... (총 $KEYFRAME_COUNT개 중 처음 20개만 표시)"
    fi
else
    echo "   키 프레임 정보를 추출할 수 없습니다."
fi

# 키프레임 간격 분석
echo ""
echo "6. 키프레임 간격 분석:"
KEYFRAME_TIMES=$(ffprobe -v quiet -select_streams v:0 \
                 -show_entries frame=pict_type,pts_time \
                 -of csv=p=0 "$VIDEO_FILE" 2>/dev/null | \
                 awk -F',' '$2 == "I" {print $1}' | grep -v "N/A" | head -10)

if [[ -n "$KEYFRAME_TIMES" ]]; then
    prev_time=""
    count=0
    total_interval=0
    
    echo "$KEYFRAME_TIMES" | while read -r current_time; do
        if [[ -n "$prev_time" ]]; then
            interval=$(echo "scale=3; $current_time - $prev_time" | bc 2>/dev/null || echo "0")
            total_interval=$(echo "scale=3; $total_interval + $interval" | bc 2>/dev/null || echo "0")
            count=$((count + 1))
            echo "   키프레임 $count-$((count+1)) 간격: ${interval}초"
        fi
        prev_time=$current_time
    done
    
    if [[ $count -gt 0 ]]; then
        avg_interval=$(echo "scale=3; $total_interval / $count" | bc 2>/dev/null || echo "계산 불가")
        echo "   평균 키프레임 간격: ${avg_interval}초"
    fi
else
    echo "   키프레임 간격을 계산할 수 없습니다."
fi

echo ""
echo "7. 프레임 번호로 시간 계산:"
echo "   예시:"

for frame in 100 300 600 900; do
    time=$(echo "scale=3; $frame / $FPS_CALC" | bc 2>/dev/null || echo "계산 불가")
    echo "   프레임 $frame = 약 $time 초 (FPS: $FPS_CALC 기준)"
done 