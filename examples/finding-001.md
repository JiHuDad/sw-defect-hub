# 예제: 오류 경로에서 메모리 해제 누락

> 이 파일은 기능 확인용 가상 Finding입니다. 실제 검사 결과가 아닙니다.

## Finding

| 항목 | 내용 |
|---|---|
| 파일 | src/example.c |
| 함수 | example_process() |
| 심각도 | Medium |

## 설명

오류 경로에서 할당된 버퍼가 해제되지 않는 상황을 가정합니다.

```c
char *buffer = allocate_buffer();
if (operation_failed()) {
    return -1; /* 가상 예제 */
}
```

## 검토 근거

- 실패 경로의 소유권을 확인합니다.
- 실제 결함인지 팀이 판단하고 웹에서 상태를 기록합니다.
