# Telegram Channel MVP Guide

## 배경
`ccoli`의 iOS 확장 전 단계로 Telegram Bot 채널 MVP를 제공합니다.

## 범위
- 메시지 수신
- LLM 응답 생성/전송
- 인증(chat id allow-list)
- 레이트리밋(min interval)

## 운영/배포
1. Telegram bot token은 코드/문서에 평문으로 저장하지 말고 `server/.env`로 관리
2. 허용 chat id 목록을 운영자가 관리
3. 전송 실패 시 사용자 메시지와 내부 디버그를 분리

## 장애 대응
- 전송 실패 증가 시 봇 토큰 재발급
- 레이트리밋 알람 빈도 증가 시 `min_interval_sec` 상향

## 롤백
- 채널 기능 비활성화
- allow-list 비우기
