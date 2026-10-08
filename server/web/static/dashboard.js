const LOCALES = {
  en: { intl: "en-US", html: "en" },
  ko: { intl: "ko-KR", html: "ko" },
  ja: { intl: "ja-JP", html: "ja" },
  zh: { intl: "zh-CN", html: "zh-CN" },
};

const COPY = {
  en: {
    meta: { title: "ccoli dashboard" },
    brand: {
      kicker: "ccoli dashboard",
      title: "Voice runtime control room.",
      body: "Switch UI language below. STT/TTS defaults stay unchanged.",
    },
    locale: { options: { en: "English", ko: "Korean", ja: "Japanese", zh: "Chinese" } },
    nav: {
      overview: { label: "Overview", body: "Live summary" },
      diagnostics: { label: "Diagnostics", body: "Runtime checks" },
      memory: { label: "Memory", body: "Editable files" },
      conversation: { label: "Conversation", body: "History and speakers" },
      schedules: { label: "Schedules", body: "Reminders and alarms" },
      chat: { label: "Chat", body: "Browser conversation" },
      logs: { label: "Logs", body: "Live stream" },
    },
    top: {
      kicker: "command center",
      title: "ccoli voice runtime",
      body: "STT · LLM · TTS pipeline status and controls.",
      localeLabel: "Language",
      reconnect: "Reconnect",
      refresh: "Refresh",
    },
    overview: {
      heroKicker: "overview",
      actions: { chat: "Open chat", memory: "Open memory" },
      metrics: {
        mode: "Mode",
        emotion: "Emotion",
        conversation: "Conversation",
        connection: "Connection",
      },
      schedules: { title: "Upcoming schedules", body: "Next reminders and timers.", action: "Open schedules" },
      conversation: { title: "Recent conversation", body: "Latest context at a glance.", action: "Open history" },
      logs: { title: "Latest logs", body: "Recent runtime events.", action: "Open logs" },
    },
    diagnostics: {
      kicker: "diagnostics",
      title: "Runtime diagnostics and controls.",
      body: "Curated settings — no raw config patching.",
      refresh: "Refresh diagnostics",
      check: "Run check",
      save: "Save changes",
      stt: {
        title: "STT",
        body: "Device, model size, and runtime notes.",
        device: "Configured device",
        modelSize: "Model size",
      },
      connection: {
        title: "Connection",
        body: "Transport status and preferred mode.",
        mode: "Connection mode",
      },
      integrations: {
        title: "Integrations",
        body: "Health checks and toggle controls.",
        refresh: "Refresh integrations",
      },
      checkResults: {
        title: "Recent checks",
        body: "Quick review of past results.",
        llmAction: "Check LLM",
      },
      advanced: {
        title: "Advanced",
        body: "Token and raw config snapshot.",
        token: "X-Auth-Token",
        tokenPlaceholder: "Enter the dashboard token if authentication is enabled.",
        saveToken: "Save token",
        clearToken: "Clear token",
        refreshConfig: "Refresh config snapshot",
      },
      options: {
        deviceCpu: "CPU",
        deviceCuda: "CUDA",
        modeAuto: "Auto",
        modeWired: "Wired",
        modeWifi: "Wi-Fi",
      },
    },
    memory: {
      kicker: "memory",
      title: "Edit assistant memory files.",
      body: "Select a file, edit in-place.",
      reload: "Reload file",
      save: "Save memory",
      filesTitle: "Files",
      filesBody: "Pick a file to load it into the editor.",
    },
    conversation: {
      kicker: "conversation",
      title: "Turn history and speakers.",
      body: "Filter by speaker or scroll through recent turns.",
      refresh: "Refresh history",
      clear: "Clear history",
      filters: {
        speaker: "Speaker filter",
        limit: "Items to load",
        allSpeakers: "All speakers",
      },
    },
    schedules: {
      kicker: "schedules",
      title: "Reminders in one place.",
      body: "Add, complete, or delete schedules.",
      refresh: "Refresh schedules",
      add: "Add schedule",
      fields: {
        title: "Title",
        titlePlaceholder: "Example: Monday demo prep",
        datetime: "Date and time",
        reminder: "Reminder lead time (minutes)",
        description: "Description",
        descriptionPlaceholder: "Optional note",
      },
    },
    chat: {
      kicker: "chat",
      title: "Talk to ccoli from the browser.",
      body: "Web chat via /api/chat.",
      composeTitle: "Send a message",
      composeBody: "Messages stay in this browser session.",
      speaker: "speaker_id",
      message: "Message",
      messagePlaceholder: "Type a message for ccoli.",
      send: "Send",
      clear: "Clear feed",
    },
    logs: {
      kicker: "logs",
      title: "Live runtime stream.",
      body: "Filter to narrow output.",
      refresh: "Refresh logs",
      tail: "Recent line count",
      filter: "Filter",
      filterPlaceholder: "Example: ERROR, websocket, STT",
    },
    common: {
      pause: "Pause",
      resume: "Resume",
      loading: "Loading...",
      empty: "Nothing to show yet.",
      open: "Open",
      enabled: "Enabled",
      disabled: "Disabled",
      configured: "Configured",
      needsConfig: "Needs config",
      connected: "Connected",
      disconnected: "Disconnected",
      unknown: "Unknown",
      notChecked: "Not checked",
      active: "Active",
      inactive: "Inactive",
      complete: "Complete",
      delete: "Delete",
      yes: "Yes",
      no: "No",
      health: "Health",
      saving: "Saved",
      tokenSaved: "Token saved.",
      tokenCleared: "Token cleared.",
      refreshed: "Dashboard refreshed.",
      refreshPartial: "Dashboard refreshed with some errors.",
      messageRequired: "Enter a message first.",
      historyCleared: "Conversation history cleared.",
      scheduleAdded: "Schedule added.",
      scheduleCompleted: "Schedule marked complete.",
      scheduleDeleted: "Schedule deleted.",
      chatReceived: "Chat response received.",
      integrationUpdated: "Integration updated.",
      diagnosticsUpdated: "Diagnostics updated.",
      saveFailed: "Save failed",
      loadFailed: "Load failed",
      actionFailed: "Action failed",
      checkCompleted: "Check completed.",
      noData: "No data yet.",
    },
  },
  ko: {
    meta: { title: "ccoli dashboard" },
    brand: {
      kicker: "ccoli 대시보드",
      title: "음성 런타임 제어실.",
      body: "UI 언어만 전환합니다. STT/TTS 기본값은 유지.",
    },
    locale: { options: { en: "English", ko: "한국어", ja: "日本語", zh: "中文" } },
    nav: {
      overview: { label: "개요", body: "라이브 요약" },
      diagnostics: { label: "진단", body: "런타임 점검" },
      memory: { label: "메모리", body: "파일 편집" },
      conversation: { label: "대화", body: "히스토리와 화자" },
      schedules: { label: "일정", body: "리마인더와 알람" },
      chat: { label: "채팅", body: "브라우저 대화" },
      logs: { label: "로그", body: "실시간 스트림" },
    },
    top: {
      kicker: "제어실",
      title: "ccoli 음성 런타임",
      body: "STT · LLM · TTS 파이프라인 상태와 제어.",
      localeLabel: "언어",
      reconnect: "재연결",
      refresh: "새로고침",
    },
    overview: {
      heroKicker: "개요",
      actions: { chat: "채팅 열기", memory: "메모리 열기" },
      metrics: { mode: "모드", emotion: "감정", conversation: "대화 수", connection: "연결" },
      schedules: { title: "다가오는 일정", body: "다음 리마인더와 타이머입니다.", action: "일정 열기" },
      conversation: { title: "최근 대화", body: "최신 대화 맥락을 빠르게 봅니다.", action: "히스토리 열기" },
      logs: { title: "최근 로그", body: "방금 발생한 런타임 이벤트입니다.", action: "로그 열기" },
    },
    diagnostics: {
      kicker: "진단",
      title: "런타임 진단과 설정.",
      body: "정리된 설정만 제공합니다.",
      refresh: "진단 새로고침",
      check: "점검 실행",
      save: "변경 저장",
      stt: {
        title: "STT",
        body: "디바이스, 모델 크기, 런타임 메모.",
        device: "설정 디바이스",
        modelSize: "모델 크기",
      },
      connection: {
        title: "연결",
        body: "전송 상태와 기본 모드.",
        mode: "연결 모드",
      },
      integrations: {
        title: "연동",
        body: "헬스 체크와 활성화 제어.",
        refresh: "연동 새로고침",
      },
      checkResults: {
        title: "최근 점검",
        body: "점검 결과 빠른 확인.",
        llmAction: "LLM 점검",
      },
      advanced: {
        title: "고급",
        body: "토큰과 raw config 스냅샷.",
        token: "X-Auth-Token",
        tokenPlaceholder: "인증이 켜져 있다면 토큰을 입력하세요.",
        saveToken: "토큰 저장",
        clearToken: "토큰 지우기",
        refreshConfig: "config 새로고침",
      },
      options: {
        deviceCpu: "CPU",
        deviceCuda: "CUDA",
        modeAuto: "자동",
        modeWired: "유선",
        modeWifi: "Wi-Fi",
      },
    },
    memory: {
      kicker: "메모리",
      title: "어시스턴트 메모리 파일 편집.",
      body: "파일 선택 후 바로 편집.",
      reload: "파일 다시 읽기",
      save: "메모리 저장",
      filesTitle: "파일 목록",
      filesBody: "파일을 선택하면 편집기에 로드됩니다.",
    },
    conversation: {
      kicker: "대화",
      title: "대화 히스토리와 화자.",
      body: "화자별 필터링, 최근 턴 확인.",
      refresh: "히스토리 새로고침",
      clear: "히스토리 비우기",
      filters: {
        speaker: "화자 필터",
        limit: "불러올 개수",
        allSpeakers: "전체 화자",
      },
    },
    schedules: {
      kicker: "일정",
      title: "리마인더 관리.",
      body: "일정 추가, 완료, 삭제.",
      refresh: "일정 새로고침",
      add: "일정 추가",
      fields: {
        title: "제목",
        titlePlaceholder: "예: 월요일 데모 준비",
        datetime: "날짜와 시간",
        reminder: "미리 알림(분)",
        description: "설명",
        descriptionPlaceholder: "선택 메모",
      },
    },
    chat: {
      kicker: "채팅",
      title: "브라우저에서 ccoli와 대화.",
      body: "/api/chat 기반 웹 채팅.",
      composeTitle: "메시지 보내기",
      composeBody: "현재 브라우저 세션에 메시지 유지.",
      speaker: "speaker_id",
      message: "메시지",
      messagePlaceholder: "ccoli에게 보낼 메시지를 입력하세요.",
      send: "보내기",
      clear: "피드 비우기",
    },
    logs: {
      kicker: "로그",
      title: "실시간 런타임 스트림.",
      body: "필터로 출력 범위 축소.",
      refresh: "로그 새로고침",
      tail: "최근 줄 수",
      filter: "필터",
      filterPlaceholder: "예: ERROR, websocket, STT",
    },
    common: {
      pause: "일시정지",
      resume: "재개",
      loading: "불러오는 중...",
      empty: "표시할 내용이 아직 없습니다.",
      open: "열기",
      enabled: "활성",
      disabled: "비활성",
      configured: "구성됨",
      needsConfig: "구성 필요",
      connected: "연결됨",
      disconnected: "연결 안 됨",
      unknown: "알 수 없음",
      notChecked: "미확인",
      active: "동작 중",
      inactive: "비활성",
      complete: "완료 처리",
      delete: "삭제",
      yes: "예",
      no: "아니오",
      health: "헬스",
      saving: "저장했습니다.",
      tokenSaved: "토큰을 저장했습니다.",
      tokenCleared: "토큰을 지웠습니다.",
      refreshed: "대시보드를 새로고침했습니다.",
      refreshPartial: "일부 오류와 함께 새로고침했습니다.",
      messageRequired: "메시지를 먼저 입력해주세요.",
      historyCleared: "대화 히스토리를 비웠습니다.",
      scheduleAdded: "일정을 추가했습니다.",
      scheduleCompleted: "일정을 완료 처리했습니다.",
      scheduleDeleted: "일정을 삭제했습니다.",
      chatReceived: "채팅 응답을 받았습니다.",
      integrationUpdated: "연동 상태를 반영했습니다.",
      diagnosticsUpdated: "진단 정보를 갱신했습니다.",
      saveFailed: "저장 실패",
      loadFailed: "로드 실패",
      actionFailed: "작업 실패",
      checkCompleted: "점검을 완료했습니다.",
      noData: "아직 데이터가 없습니다.",
    },
  },
  ja: {
    meta: { title: "ccoli dashboard" },
    brand: {
      kicker: "ccoli ダッシュボード",
      title: "音声ランタイム制御室。",
      body: "UI言語のみ切替。STT/TTSの既定値は維持。",
    },
    locale: { options: { en: "English", ko: "韓国語", ja: "日本語", zh: "中国語" } },
    nav: {
      overview: { label: "概要", body: "ライブ要約" },
      diagnostics: { label: "診断", body: "ランタイム確認" },
      memory: { label: "メモリ", body: "ファイル編集" },
      conversation: { label: "会話", body: "履歴と話者" },
      schedules: { label: "予定", body: "リマインダー" },
      chat: { label: "チャット", body: "ブラウザ会話" },
      logs: { label: "ログ", body: "ライブ出力" },
    },
    top: {
      kicker: "制御室",
      title: "ccoli 音声ランタイム",
      body: "STT · LLM · TTS パイプラインの状態と制御。",
      localeLabel: "言語",
      reconnect: "再接続",
      refresh: "更新",
    },
    overview: {
      heroKicker: "概要",
      actions: { chat: "チャットを開く", memory: "メモリを開く" },
      metrics: { mode: "モード", emotion: "感情", conversation: "会話数", connection: "接続" },
      schedules: { title: "今後の予定", body: "次のリマインダーとタイマー。", action: "予定を開く" },
      conversation: { title: "最近の会話", body: "最新の文脈をすばやく確認。", action: "履歴を開く" },
      logs: { title: "最近のログ", body: "直近のランタイムイベント。", action: "ログを開く" },
    },
    diagnostics: {
      kicker: "診断",
      title: "ランタイム診断と設定。",
      body: "整理された設定のみ提供。",
      refresh: "診断を更新",
      check: "チェック実行",
      save: "変更を保存",
      stt: {
        title: "STT",
        body: "デバイス、モデルサイズ、メモ。",
        device: "設定デバイス",
        modelSize: "モデルサイズ",
      },
      connection: {
        title: "接続",
        body: "転送状態と基本モード。",
        mode: "接続モード",
      },
      integrations: {
        title: "連携",
        body: "ヘルスチェックと有効化。",
        refresh: "連携を更新",
      },
      checkResults: {
        title: "最近のチェック",
        body: "結果の簡易確認。",
        llmAction: "LLM を確認",
      },
      advanced: {
        title: "詳細設定",
        body: "トークンとraw configスナップショット。",
        token: "X-Auth-Token",
        tokenPlaceholder: "認証が有効ならトークンを入力してください。",
        saveToken: "トークン保存",
        clearToken: "トークン削除",
        refreshConfig: "config 更新",
      },
      options: {
        deviceCpu: "CPU",
        deviceCuda: "CUDA",
        modeAuto: "自動",
        modeWired: "有線",
        modeWifi: "Wi-Fi",
      },
    },
    memory: {
      kicker: "メモリ",
      title: "メモリファイル編集。",
      body: "ファイル選択後、直接編集。",
      reload: "再読み込み",
      save: "メモリ保存",
      filesTitle: "ファイル",
      filesBody: "ファイルを選ぶとエディタへ読み込みます。",
    },
    conversation: {
      kicker: "会話",
      title: "会話履歴と話者。",
      body: "話者フィルタ、最近のターン確認。",
      refresh: "履歴更新",
      clear: "履歴削除",
      filters: {
        speaker: "話者フィルタ",
        limit: "読み込み件数",
        allSpeakers: "すべての話者",
      },
    },
    schedules: {
      kicker: "予定",
      title: "リマインダー管理。",
      body: "予定の追加・完了・削除。",
      refresh: "予定更新",
      add: "予定追加",
      fields: {
        title: "タイトル",
        titlePlaceholder: "例: 月曜デモ準備",
        datetime: "日時",
        reminder: "事前通知（分）",
        description: "説明",
        descriptionPlaceholder: "任意メモ",
      },
    },
    chat: {
      kicker: "チャット",
      title: "ブラウザからccoliと会話。",
      body: "/api/chat経由のWebチャット。",
      composeTitle: "メッセージ送信",
      composeBody: "このブラウザセッションにメッセージ保持。",
      speaker: "speaker_id",
      message: "メッセージ",
      messagePlaceholder: "ccoli へのメッセージを入力してください。",
      send: "送信",
      clear: "フィードを消去",
    },
    logs: {
      kicker: "ログ",
      title: "ライブランタイムストリーム。",
      body: "フィルタで出力を絞り込み。",
      refresh: "ログ更新",
      tail: "行数",
      filter: "フィルタ",
      filterPlaceholder: "例: ERROR, websocket, STT",
    },
    common: {
      pause: "一時停止",
      resume: "再開",
      loading: "読み込み中...",
      empty: "まだ表示できる内容がありません。",
      open: "開く",
      enabled: "有効",
      disabled: "無効",
      configured: "設定済み",
      needsConfig: "設定必要",
      connected: "接続中",
      disconnected: "未接続",
      unknown: "不明",
      notChecked: "未確認",
      active: "動作中",
      inactive: "無効",
      complete: "完了",
      delete: "削除",
      yes: "はい",
      no: "いいえ",
      health: "ヘルス",
      saving: "保存しました。",
      tokenSaved: "トークンを保存しました。",
      tokenCleared: "トークンを消去しました。",
      refreshed: "ダッシュボードを更新しました。",
      refreshPartial: "一部エラー付きで更新しました。",
      messageRequired: "先にメッセージを入力してください。",
      historyCleared: "会話履歴を消去しました。",
      scheduleAdded: "予定を追加しました。",
      scheduleCompleted: "予定を完了にしました。",
      scheduleDeleted: "予定を削除しました。",
      chatReceived: "チャット応答を受信しました。",
      integrationUpdated: "連携状態を反映しました。",
      diagnosticsUpdated: "診断情報を更新しました。",
      saveFailed: "保存失敗",
      loadFailed: "読み込み失敗",
      actionFailed: "操作失敗",
      checkCompleted: "チェックが完了しました。",
      noData: "まだデータがありません。",
    },
  },
  zh: {
    meta: { title: "ccoli dashboard" },
    brand: {
      kicker: "ccoli 仪表板",
      title: "语音运行时控制室。",
      body: "仅切换UI语言。STT/TTS默认值不变。",
    },
    locale: { options: { en: "English", ko: "韩语", ja: "日语", zh: "中文" } },
    nav: {
      overview: { label: "总览", body: "实时摘要" },
      diagnostics: { label: "诊断", body: "运行时检查" },
      memory: { label: "记忆", body: "文件编辑" },
      conversation: { label: "对话", body: "历史与说话人" },
      schedules: { label: "日程", body: "提醒与闹钟" },
      chat: { label: "聊天", body: "浏览器会话" },
      logs: { label: "日志", body: "实时输出" },
    },
    top: {
      kicker: "控制室",
      title: "ccoli 语音运行时",
      body: "STT · LLM · TTS 管道状态与控制。",
      localeLabel: "语言",
      reconnect: "重新连接",
      refresh: "刷新",
    },
    overview: {
      heroKicker: "总览",
      actions: { chat: "打开聊天", memory: "打开记忆" },
      metrics: { mode: "模式", emotion: "情绪", conversation: "对话数", connection: "连接" },
      schedules: { title: "即将到来的日程", body: "下一批提醒和计时器。", action: "打开日程" },
      conversation: { title: "最近对话", body: "快速查看最新上下文。", action: "打开历史" },
      logs: { title: "最近日志", body: "刚刚发生的运行时事件。", action: "打开日志" },
    },
    diagnostics: {
      kicker: "诊断",
      title: "运行时诊断与设置。",
      body: "精简设置，无需手动patch。",
      refresh: "刷新诊断",
      check: "执行检查",
      save: "保存更改",
      stt: {
        title: "STT",
        body: "设备、模型大小、运行时说明。",
        device: "配置设备",
        modelSize: "模型大小",
      },
      connection: {
        title: "连接",
        body: "传输状态与首选模式。",
        mode: "连接模式",
      },
      integrations: {
        title: "集成",
        body: "健康检查与启用控制。",
        refresh: "刷新集成",
      },
      checkResults: {
        title: "最近检查",
        body: "结果快速查看。",
        llmAction: "检查 LLM",
      },
      advanced: {
        title: "高级",
        body: "令牌与raw config快照。",
        token: "X-Auth-Token",
        tokenPlaceholder: "如果启用了认证，请在这里输入令牌。",
        saveToken: "保存令牌",
        clearToken: "清除令牌",
        refreshConfig: "刷新 config",
      },
      options: {
        deviceCpu: "CPU",
        deviceCuda: "CUDA",
        modeAuto: "自动",
        modeWired: "有线",
        modeWifi: "Wi-Fi",
      },
    },
    memory: {
      kicker: "记忆",
      title: "编辑记忆文件。",
      body: "选择文件后直接编辑。",
      reload: "重新加载文件",
      save: "保存记忆",
      filesTitle: "文件列表",
      filesBody: "选择文件后加载到编辑器。",
    },
    conversation: {
      kicker: "对话",
      title: "对话历史与说话人。",
      body: "按说话人筛选，查看最近轮次。",
      refresh: "刷新历史",
      clear: "清空历史",
      filters: {
        speaker: "说话人筛选",
        limit: "加载数量",
        allSpeakers: "全部说话人",
      },
    },
    schedules: {
      kicker: "日程",
      title: "提醒管理。",
      body: "添加、完成、删除日程。",
      refresh: "刷新日程",
      add: "添加日程",
      fields: {
        title: "标题",
        titlePlaceholder: "例如：周一演示准备",
        datetime: "日期时间",
        reminder: "提前提醒（分钟）",
        description: "说明",
        descriptionPlaceholder: "可选备注",
      },
    },
    chat: {
      kicker: "聊天",
      title: "在浏览器与ccoli对话。",
      body: "基于/api/chat的Web聊天。",
      composeTitle: "发送消息",
      composeBody: "消息保留在当前浏览器会话。",
      speaker: "speaker_id",
      message: "消息",
      messagePlaceholder: "输入发给 ccoli 的消息。",
      send: "发送",
      clear: "清空内容",
    },
    logs: {
      kicker: "日志",
      title: "实时运行时输出。",
      body: "过滤器缩小输出范围。",
      refresh: "刷新日志",
      tail: "最近行数",
      filter: "过滤",
      filterPlaceholder: "例如：ERROR, websocket, STT",
    },
    common: {
      pause: "暂停",
      resume: "继续",
      loading: "加载中...",
      empty: "暂时没有可显示的内容。",
      open: "打开",
      enabled: "已启用",
      disabled: "已禁用",
      configured: "已配置",
      needsConfig: "需要配置",
      connected: "已连接",
      disconnected: "未连接",
      unknown: "未知",
      notChecked: "未检查",
      active: "运行中",
      inactive: "未激活",
      complete: "完成",
      delete: "删除",
      yes: "是",
      no: "否",
      health: "健康",
      saving: "已保存。",
      tokenSaved: "已保存令牌。",
      tokenCleared: "已清除令牌。",
      refreshed: "已刷新仪表板。",
      refreshPartial: "刷新完成，但有部分错误。",
      messageRequired: "请先输入消息。",
      historyCleared: "已清空对话历史。",
      scheduleAdded: "已添加日程。",
      scheduleCompleted: "已将日程标记为完成。",
      scheduleDeleted: "已删除日程。",
      chatReceived: "已收到聊天响应。",
      integrationUpdated: "已更新集成状态。",
      diagnosticsUpdated: "已更新诊断信息。",
      saveFailed: "保存失败",
      loadFailed: "加载失败",
      actionFailed: "操作失败",
      checkCompleted: "检查已完成。",
      noData: "暂时没有数据。",
    },
  },
};

const STATE = {
  locale: normalizeLocale(localStorage.getItem("ccoli.locale") || "en"),
  tab: normalizeTab(localStorage.getItem("ccoli.activeTab") || "overview"),
  token: localStorage.getItem("ccoli.authToken") || "",
  authGeneration: 0,
  theme: localStorage.getItem("ccoli.theme") || "dark",
  memoryFile: localStorage.getItem("ccoli.activeMemory") || "Soul.md",
  status: null,
  diagnostics: null,
  integrations: {},
  integrationHealth: {},
  conversations: [],
  schedules: [],
  logs: [],
  chat: [],
  configSnapshot: null,
  ws: null,
  wsHeartbeat: null,
  wsRetry: null,
  wsAuthBlocked: false,
  logsPaused: false,
  lastChatSignature: "",
};

document.addEventListener("DOMContentLoaded", boot);

function boot() {
  applyTheme(STATE.theme);
  bind();
  $("#auth-token").value = STATE.token;
  $("#locale-select").value = STATE.locale;
  seedDate();
  applyCopy();
  renderChat();
  renderLogs();
  openTab(STATE.tab);
  connectWs();
  refreshAll(true);
  window.setInterval(() => fetchStatus(true), 15000);
  window.setInterval(() => fetchDiagnostics(true), 20000);
  window.setInterval(() => fetchSchedules(true), 45000);
  window.setInterval(() => fetchConversation(true), 30000);
  window.setInterval(() => {
    if (!STATE.logsPaused) fetchLogs(true);
  }, 18000);
}

function bind() {
  $("#nav").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) openTab(button.dataset.tab);
  });
  $("#refresh-all").addEventListener("click", () => refreshAll());
  $("#connect-ws").addEventListener("click", () => connectWs(true));
  $("#theme-toggle").addEventListener("click", toggleTheme);
  $("#locale-select").addEventListener("change", (event) => {
    STATE.locale = normalizeLocale(event.target.value);
    localStorage.setItem("ccoli.locale", STATE.locale);
    applyCopy();
    renderAll();
  });
  $("#diagnostics-refresh").addEventListener("click", () => refreshDiagnostics());
  $("#stt-settings-form").addEventListener("submit", saveSttSettings);
  $("#connection-settings-form").addEventListener("submit", saveConnectionSettings);
  $("#stt-check").addEventListener("click", () => runDiagnosticCheck("stt"));
  $("#connection-check").addEventListener("click", () => runDiagnosticCheck("connection"));
  $("#llm-check").addEventListener("click", () => runDiagnosticCheck("llm"));
  $("#integrations-refresh").addEventListener("click", () => fetchIntegrations());
  $("#save-token").addEventListener("click", saveToken);
  $("#clear-token").addEventListener("click", clearToken);
  $("#config-refresh").addEventListener("click", () => fetchConfig());

  $("#reload-memory").addEventListener("click", () => loadMemory(STATE.memoryFile));
  $("#save-memory").addEventListener("click", saveMemory);

  $("#conversation-refresh").addEventListener("click", () => fetchConversation());
  $("#conversation-clear").addEventListener("click", clearConversation);
  $("#speaker-filter").addEventListener("change", () => fetchConversation());
  $("#conversation-limit").addEventListener("change", () => fetchConversation());

  $("#schedules-refresh").addEventListener("click", () => fetchSchedules());
  $("#schedule-form").addEventListener("submit", createSchedule);

  $("#chat-form").addEventListener("submit", sendChat);
  $("#chat-clear").addEventListener("click", clearChat);

  $("#logs-refresh").addEventListener("click", () => fetchLogs());
  $("#logs-pause").addEventListener("click", toggleLogs);
  $("#log-tail").addEventListener("change", () => fetchLogs());
  $("#log-filter").addEventListener("input", renderLogs);

  document.body.addEventListener("click", (event) => {
    const tabTrigger = event.target.closest("[data-tab-target]");
    if (tabTrigger) {
      openTab(tabTrigger.dataset.tabTarget);
      if (tabTrigger.dataset.memoryFile) loadMemory(tabTrigger.dataset.memoryFile);
      return;
    }

    const memoryButton = event.target.closest("[data-memory-file-button]");
    if (memoryButton) {
      loadMemory(memoryButton.dataset.memoryFileButton);
      return;
    }

    const scheduleAction = event.target.closest("[data-schedule-action]");
    if (scheduleAction) {
      const scheduleId = Number(scheduleAction.dataset.scheduleId);
      if (scheduleAction.dataset.scheduleAction === "complete") {
        completeSchedule(scheduleId);
      } else {
        deleteSchedule(scheduleId);
      }
      return;
    }

    const integrationAction = event.target.closest("[data-integration-action]");
    if (integrationAction) {
      const name = integrationAction.dataset.integrationName;
      if (integrationAction.dataset.integrationAction === "health") {
        checkIntegration(name);
      } else {
        toggleIntegration(name, integrationAction.dataset.integrationEnabled !== "true");
      }
    }
  });
}

function normalizeLocale(value) {
  return Object.prototype.hasOwnProperty.call(LOCALES, value) ? value : "en";
}

function normalizeTab(value) {
  return value === "settings" ? "diagnostics" : value;
}

function $(selector, root = document) {
  return root.querySelector(selector);
}

function $$(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

function copyFor(locale = STATE.locale) {
  return COPY[locale] || COPY.en;
}

function resolveCopy(path, locale = STATE.locale) {
  return path.split(".").reduce((current, part) => (current && current[part] !== undefined ? current[part] : undefined), copyFor(locale));
}

function t(path, fallback = "") {
  const value = resolveCopy(path);
  return typeof value === "string" ? value : fallback;
}

function uiLocale() {
  return LOCALES[STATE.locale]?.intl || LOCALES.en.intl;
}

function applyCopy() {
  document.documentElement.lang = LOCALES[STATE.locale]?.html || "en";
  document.title = t("meta.title", "ccoli dashboard");

  $$("[data-i18n]").forEach((node) => {
    const value = t(node.dataset.i18n, "");
    if (value) node.textContent = value;
  });
  $$("[data-i18n-placeholder]").forEach((node) => {
    const value = t(node.dataset.i18nPlaceholder, "");
    if (value) node.setAttribute("placeholder", value);
  });

  $("#logs-pause").textContent = STATE.logsPaused ? t("common.resume") : t("common.pause");
  if ($("#locale-select").value !== STATE.locale) $("#locale-select").value = STATE.locale;
}

function renderAll() {
  renderStatus();
  renderDiagnostics();
  renderMemoryList();
  $("#memory-meta").textContent = $("#memory-editor").value ? `${formatNumber($("#memory-editor").value.length)} ${uiLabel("chars")}` : $("#memory-meta").textContent;
  renderConversation();
  renderSchedules();
  renderOverviewConversation();
  renderOverviewSchedules();
  renderOverviewLogs();
  renderIntegrations();
  renderChat();
  renderLogs();
  renderConfigSnapshot();
}

function openTab(tab) {
  STATE.tab = normalizeTab(tab);
  localStorage.setItem("ccoli.activeTab", STATE.tab);
  $$("#nav button").forEach((button) => button.classList.toggle("active", button.dataset.tab === STATE.tab));
  $$(".tab").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${STATE.tab}`));
  if (STATE.tab === "diagnostics") refreshDiagnostics(true);
  if (STATE.tab === "logs") fetchLogs(true);
  if (STATE.tab === "conversation") fetchConversation(true);
}

function applyTheme(theme) {
  STATE.theme = theme;
  if (theme === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  const icon = $("#theme-icon");
  if (icon) icon.textContent = theme === "dark" ? "☀️" : "🌙";
}

function toggleTheme() {
  const next = STATE.theme === "dark" ? "light" : "dark";
  localStorage.setItem("ccoli.theme", next);
  applyTheme(next);
}

async function refreshAll(silent = false) {
  const results = await Promise.allSettled([
    fetchStatus(true),
    fetchDiagnostics(true),
    fetchMemoryList(true),
    loadMemory(STATE.memoryFile, true),
    fetchSpeakers(true),
    fetchConversation(true),
    fetchSchedules(true),
    fetchIntegrations(true),
    fetchLogs(true),
    fetchConfig(true),
  ]);
  const failures = results.filter((item) => item.status === "rejected").length;
  if (!silent) toast(failures ? t("common.refreshPartial") : t("common.refreshed"));
}

async function refreshDiagnostics(silent = false) {
  const results = await Promise.allSettled([fetchDiagnostics(true), fetchIntegrations(true), fetchConfig(true)]);
  const failures = results.filter((item) => item.status === "rejected").length;
  if (!silent) toast(failures ? t("common.refreshPartial") : t("common.diagnosticsUpdated"));
}

async function api(path, options = {}) {
  const generation = STATE.authGeneration;
  const headers = new Headers(options.headers || {});
  if (STATE.token) {
    headers.set("X-Auth-Token", utf8Base64Url(STATE.token));
    headers.set("X-Auth-Token-Encoding", "utf8-base64url");
  }
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response;
  let payload;
  try {
    response = await fetch(path, { ...options, headers });
    if (generation !== STATE.authGeneration) throw new StaleAuthResponse();
    const contentType = response.headers.get("content-type") || "";
    payload = contentType.includes("application/json") ? await response.json() : await response.text();
  } catch (error) {
    if (generation !== STATE.authGeneration) throw new StaleAuthResponse();
    throw error;
  }
  if (generation !== STATE.authGeneration) throw new StaleAuthResponse();
  if (!response.ok) {
    const detail = typeof payload === "string" ? payload : payload.detail || JSON.stringify(payload);
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return payload;
}

class StaleAuthResponse extends Error {}

function utf8Base64Url(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function fetchStatus(silent = false) {
  try {
    STATE.status = await api("/api/status");
    renderStatus();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

async function fetchDiagnostics(silent = false) {
  try {
    STATE.diagnostics = await api("/api/diagnostics/");
    syncDiagnosticsControls();
    renderDiagnostics();
    renderStatus();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

async function runDiagnosticCheck(target) {
  try {
    const result = await api("/api/diagnostics/check", {
      method: "POST",
      body: JSON.stringify({ target }),
    });
    if (!STATE.diagnostics) STATE.diagnostics = { runtime: {}, stt: {}, connection: {}, last_checks: {} };
    STATE.diagnostics.last_checks = STATE.diagnostics.last_checks || {};
    STATE.diagnostics.last_checks[target] = result;
    renderDiagnostics();
    toast(result.summary || t("common.checkCompleted"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

function syncDiagnosticsControls() {
  const diagnostics = STATE.diagnostics || {};
  const stt = diagnostics.stt || {};
  const connection = diagnostics.connection || {};

  if (stt.configured_device) $("#stt-device").value = stt.configured_device;
  if (stt.model_size) $("#stt-model-size").value = stt.model_size;
  if (connection.mode) $("#connection-mode").value = connection.mode;
}

async function saveSttSettings(event) {
  event.preventDefault();
  try {
    await api("/api/config/", {
      method: "PATCH",
      body: JSON.stringify({ section: "stt", key: "device", value: $("#stt-device").value }),
    });
    await api("/api/config/", {
      method: "PATCH",
      body: JSON.stringify({ section: "stt", key: "model_size", value: $("#stt-model-size").value }),
    });
    await Promise.allSettled([fetchDiagnostics(true), fetchConfig(true), fetchStatus(true)]);
    toast(t("common.saving"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.saveFailed")}: ${error.message}`);
  }
}

async function saveConnectionSettings(event) {
  event.preventDefault();
  try {
    await api("/api/config/", {
      method: "PATCH",
      body: JSON.stringify({ section: "connection", key: "mode", value: $("#connection-mode").value }),
    });
    await Promise.allSettled([fetchDiagnostics(true), fetchConfig(true), fetchStatus(true)]);
    toast(t("common.saving"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.saveFailed")}: ${error.message}`);
  }
}

async function fetchConfig(silent = false) {
  try {
    STATE.configSnapshot = await api("/api/config/");
    renderConfigSnapshot();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

function renderConfigSnapshot() {
  $("#config-json").textContent = STATE.configSnapshot ? JSON.stringify(STATE.configSnapshot, null, 2) : t("common.loading");
}

async function fetchIntegrations(silent = false) {
  try {
    const payload = await api("/api/integrations/");
    STATE.integrations = payload.integrations || {};
    renderIntegrations();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

async function toggleIntegration(name, enabled) {
  try {
    await api(`/api/integrations/${encodeURIComponent(name)}/enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
    STATE.integrations[name] = { ...(STATE.integrations[name] || {}), enabled };
    renderIntegrations();
    toast(t("common.integrationUpdated"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

async function checkIntegration(name) {
  try {
    const payload = await api(`/api/integrations/${encodeURIComponent(name)}/health`);
    STATE.integrationHealth[name] = {
      ok: payload.ok,
      text: payload.ok ? t("common.connected") : (payload.error ? JSON.stringify(payload.error) : t("common.unknown")),
    };
    renderIntegrations();
    toast(t("common.checkCompleted"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    STATE.integrationHealth[name] = { ok: false, text: error.message };
    renderIntegrations();
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

function renderIntegrations() {
  const root = $("#integration-list");
  const names = Object.keys(STATE.integrations || {});
  if (!names.length) {
    root.innerHTML = emptyState(t("common.noData"));
    return;
  }

  root.innerHTML = names.map((name) => {
    const integration = STATE.integrations[name] || {};
    const health = STATE.integrationHealth[name];
    const healthText = health ? health.text : t("common.notChecked");
    const enabled = !!integration.enabled;
    const configured = !!integration.configured;
    return `
      <article class="integration-item">
        <strong>${escapeHTML(name)}</strong>
        <p class="body-copy">${escapeHTML(configured ? t("common.configured") : t("common.needsConfig"))} · ${escapeHTML(enabled ? t("common.enabled") : t("common.disabled"))}</p>
        <div class="badge-row">
          <span class="badge">${escapeHTML(t("common.health"))}: ${escapeHTML(healthText)}</span>
        </div>
        <div class="action-wrap">
          <button class="btn secondary small" type="button" data-integration-action="health" data-integration-name="${escapeHTML(name)}">${escapeHTML(t("diagnostics.check"))}</button>
          <button class="btn ${enabled ? "ghost" : "primary"} small" type="button" data-integration-action="toggle" data-integration-name="${escapeHTML(name)}" data-integration-enabled="${enabled ? "true" : "false"}">${escapeHTML(enabled ? t("common.disabled") : t("common.enabled"))}</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderDiagnostics() {
  const diagnostics = STATE.diagnostics;
  if (!diagnostics) {
    $("#runtime-summary-cards").innerHTML = summaryCard(t("common.loading"), "—", t("common.loading"));
    $("#stt-summary-list").innerHTML = detailListHtml([[t("common.loading"), t("common.loading")]]);
    $("#connection-summary-list").innerHTML = detailListHtml([[t("common.loading"), t("common.loading")]]);
    $("#diagnostic-checks").innerHTML = emptyState(t("common.loading"));
    return;
  }

  const runtime = diagnostics.runtime || {};
  const warmup = runtime.warmup || {};
  const llm = runtime.llm || {};
  const stt = diagnostics.stt || {};
  const connection = diagnostics.connection || {};

  $("#runtime-summary-cards").innerHTML = [
    summaryCard(uiLabel("mode"), modeLabel(diagnostics.mode || "agent"), heroHeadline()),
    summaryCard(uiLabel("warmup"), warmupSummary(warmup), warmup.updated_at ? formatDate(warmup.updated_at) : t("common.noData")),
    summaryCard(uiLabel("llm"), llm.active_provider || llm.configured_provider || t("common.unknown"), llm.active_model || llm.configured_model || t("common.noData")),
    summaryCard(uiLabel("connection"), connection.connected ? transportLabel(connection.current_transport) : t("common.disconnected"), connection.current_endpoint || connection.last_endpoint || t("common.noData")),
  ].join("");

  $("#stt-summary-list").innerHTML = detailListHtml([
    [uiLabel("modelSize"), stt.model_size || t("common.unknown")],
    [uiLabel("configuredDevice"), stt.configured_device || t("common.unknown")],
    [uiLabel("resolvedOrder"), arrayOrFallback(stt.resolved_devices)],
    [uiLabel("deviceInUse"), stt.device_in_use || t("common.unknown")],
    [uiLabel("language"), stt.language || t("common.unknown")],
    [uiLabel("runtimeNotes"), arrayOrFallback(stt.notes)],
  ]);

  $("#connection-summary-list").innerHTML = detailListHtml([
    [uiLabel("mode"), connection.mode || t("common.unknown")],
    [uiLabel("priority"), arrayOrFallback(connection.priority)],
    [uiLabel("connected"), yesNo(connection.connected)],
    [uiLabel("currentTransport"), transportLabel(connection.current_transport)],
    [uiLabel("endpoint"), connection.current_endpoint || connection.last_endpoint || t("common.unknown")],
    [uiLabel("lastConnected"), connection.last_connected_at ? formatDate(connection.last_connected_at) : t("common.noData")],
  ]);

  const checks = diagnostics.last_checks || {};
  const names = Object.keys(checks);
  $("#diagnostic-checks").innerHTML = names.length ? names.map((target) => {
    const result = checks[target];
    return `
      <article class="data-item">
        <strong>${escapeHTML(target.toUpperCase())}</strong>
        <p class="body-copy">${escapeHTML(result.summary || t("common.noData"))}</p>
        <div class="badge-row">
          <span class="badge">${escapeHTML(result.ok ? t("common.connected") : t("common.disconnected"))}</span>
          <span class="badge">${escapeHTML(result.checked_at ? formatDate(result.checked_at) : t("common.noData"))}</span>
        </div>
      </article>
    `;
  }).join("") : emptyState(t("common.noData"));
}

function summaryCard(label, value, body) {
  return `
    <article class="metric-card surface">
      <p class="metric-label">${escapeHTML(label)}</p>
      <div class="metric-value">${escapeHTML(value)}</div>
      <p class="body-copy">${escapeHTML(body)}</p>
    </article>
  `;
}

function detailListHtml(rows) {
  return rows.map(([label, value]) => `<dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd>`).join("");
}

async function fetchMemoryList(silent = false) {
  try {
    const payload = await api("/api/memory/");
    STATE.memoryFiles = Array.isArray(payload.files) ? payload.files : [];
    renderMemoryList();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

function renderMemoryList() {
  const root = $("#memory-list");
  const files = STATE.memoryFiles || [];
  if (!files.length) {
    root.innerHTML = emptyState(t("common.noData"));
    return;
  }
  root.innerHTML = files.map((file) => `
    <button class="memory-item ${file.filename === STATE.memoryFile ? "active" : ""}" type="button" data-memory-file-button="${escapeHTML(file.filename)}">
      <span>
        <strong>${escapeHTML(file.filename)}</strong>
        <span class="body-copy">${formatNumber(file.size)} ${escapeHTML(uiLabel("chars"))}</span>
      </span>
      <span class="badge">${escapeHTML(t("common.open"))}</span>
    </button>
  `).join("");
}

async function loadMemory(file = STATE.memoryFile, silent = false) {
  try {
    const payload = await api(`/api/memory/${encodeURIComponent(file)}`);
    STATE.memoryFile = payload.filename || file;
    localStorage.setItem("ccoli.activeMemory", STATE.memoryFile);
    $("#memory-title").textContent = STATE.memoryFile;
    $("#memory-meta").textContent = `${formatNumber((payload.content || "").length)} ${uiLabel("chars")}`;
    $("#memory-editor").value = payload.content || "";
    renderMemoryList();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

async function saveMemory() {
  try {
    const content = $("#memory-editor").value;
    await api(`/api/memory/${encodeURIComponent(STATE.memoryFile)}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
    $("#memory-meta").textContent = `${formatNumber(content.length)} ${uiLabel("chars")}`;
    toast(t("common.saving"));
    fetchMemoryList(true);
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.saveFailed")}: ${error.message}`);
  }
}

async function fetchSpeakers(silent = false) {
  try {
    const payload = await api("/api/conversation/speakers");
    const speakers = Array.isArray(payload.speakers) ? payload.speakers : [];
    const select = $("#speaker-filter");
    const current = select.value;
    select.innerHTML = `<option value="">${escapeHTML(t("conversation.filters.allSpeakers"))}</option>` +
      speakers.map((speaker) => `<option value="${escapeHTML(speaker)}">${escapeHTML(speaker)}</option>`).join("");
    if (speakers.includes(current)) select.value = current;
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

async function fetchConversation(silent = false) {
  try {
    const params = new URLSearchParams({ limit: String(Number($("#conversation-limit").value || 50)) });
    const speaker = $("#speaker-filter").value;
    if (speaker) params.set("speaker_id", speaker);
    const payload = await api(`/api/conversation/?${params.toString()}`);
    STATE.conversations = Array.isArray(payload.history) ? payload.history : [];
    renderConversation();
    renderOverviewConversation();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

function renderConversation() {
  const root = $("#conversation-list");
  if (!STATE.conversations.length) {
    root.innerHTML = emptyState(t("common.noData"));
    return;
  }
  root.innerHTML = STATE.conversations.map((item) => {
    const normalized = normalizeConversation(item);
    return `
      <article class="conversation-item">
        <strong>${escapeHTML(roleLabel(normalized.role))}</strong>
        <p>${escapeHTML(normalized.content)}</p>
        <p class="body-copy">${escapeHTML(normalized.timestamp ? formatDate(normalized.timestamp) : t("common.unknown"))}</p>
      </article>
    `;
  }).join("");
}

async function clearConversation() {
  if (!window.confirm(confirmMessage("conversation"))) return;
  try {
    await api("/api/conversation/", { method: "DELETE" });
    STATE.conversations = [];
    renderConversation();
    renderOverviewConversation();
    toast(t("common.historyCleared"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

async function fetchSchedules(silent = false) {
  try {
    const payload = await api("/api/schedules/");
    STATE.schedules = Array.isArray(payload.schedules)
      ? payload.schedules.slice().sort((a, b) => String(a.datetime || "").localeCompare(String(b.datetime || "")))
      : [];
    renderSchedules();
    renderOverviewSchedules();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

function renderSchedules() {
  const root = $("#schedule-list");
  if (!STATE.schedules.length) {
    root.innerHTML = emptyState(t("common.noData"));
    return;
  }
  root.innerHTML = STATE.schedules.map((schedule) => `
    <article class="schedule-item">
      <strong>${escapeHTML(schedule.title || t("common.unknown"))}</strong>
      <p class="body-copy">${escapeHTML(formatDate(schedule.datetime))}</p>
      <p>${escapeHTML(schedule.description || t("common.noData"))}</p>
      <div class="badge-row">
        <span class="badge">${escapeHTML(schedule.completed ? t("common.complete") : t("common.active"))}</span>
        <span class="badge">${escapeHTML(`${formatNumber(schedule.reminder_before || 0)} ${uiLabel("minutes")}`)}</span>
      </div>
      <div class="action-wrap">
        ${schedule.completed ? "" : `<button class="btn secondary small" type="button" data-schedule-action="complete" data-schedule-id="${Number(schedule.id)}">${escapeHTML(t("common.complete"))}</button>`}
        <button class="btn danger small" type="button" data-schedule-action="delete" data-schedule-id="${Number(schedule.id)}">${escapeHTML(t("common.delete"))}</button>
      </div>
    </article>
  `).join("");
}

async function createSchedule(event) {
  event.preventDefault();
  try {
    await api("/api/schedules/", {
      method: "POST",
      body: JSON.stringify({
        title: $("#schedule-title").value.trim(),
        datetime: $("#schedule-datetime").value,
        description: $("#schedule-description").value.trim(),
        reminder_before: Number($("#schedule-reminder").value || 0),
      }),
    });
    $("#schedule-form").reset();
    seedDate();
    fetchSchedules(true);
    toast(t("common.scheduleAdded"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

async function completeSchedule(id) {
  try {
    await api(`/api/schedules/${id}/complete`, { method: "POST" });
    fetchSchedules(true);
    toast(t("common.scheduleCompleted"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

async function deleteSchedule(id) {
  if (!window.confirm(confirmMessage("schedule"))) return;
  try {
    await api(`/api/schedules/${id}`, { method: "DELETE" });
    fetchSchedules(true);
    toast(t("common.scheduleDeleted"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

async function sendChat(event) {
  event.preventDefault();
  const speaker = $("#chat-speaker").value.trim() || "web_user";
  const text = $("#chat-input").value.trim();
  if (!text) {
    toast(t("common.messageRequired"));
    return;
  }
  appendChat("user", text, { speaker });
  $("#chat-input").value = "";
  try {
    const payload = await api("/api/chat/", {
      method: "POST",
      body: JSON.stringify({ text, speaker_id: speaker }),
    });
    STATE.lastChatSignature = `${speaker}::${text}::${payload.response || ""}`;
    appendChat("assistant", payload.response || "", { emotion: payload.emotion, intent: payload.intent });
    toast(t("common.chatReceived"));
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    appendChat("assistant", `Error: ${error.message}`, { emotion: "error" });
    toast(`${t("common.actionFailed")}: ${error.message}`);
  }
}

function appendChat(role, text, extra = {}) {
  STATE.chat.push({ role, text, timestamp: new Date().toISOString(), ...extra });
  STATE.chat = STATE.chat.slice(-60);
  renderChat();
}

function clearChat() {
  STATE.chat = [];
  renderChat();
}

function renderChat() {
  const root = $("#chat-feed");
  if (!STATE.chat.length) {
    root.innerHTML = emptyState(t("common.noData"));
    return;
  }
  root.innerHTML = STATE.chat.map((message) => `
    <article class="chat-bubble ${message.role === "assistant" ? "assistant" : ""}">
      <p>${escapeHTML(message.text)}</p>
      <p class="body-copy">${escapeHTML(`${roleLabel(message.role)} · ${formatDate(message.timestamp)}`)}</p>
    </article>
  `).join("");
  root.scrollTop = root.scrollHeight;
}

async function fetchLogs(silent = false) {
  try {
    const payload = await api(`/api/logs/?tail=${Number($("#log-tail").value || 150)}`);
    STATE.logs = Array.isArray(payload.lines) ? payload.lines.slice(-500) : [];
    renderLogs();
    renderOverviewLogs();
  } catch (error) {
    if (error instanceof StaleAuthResponse) return;
    if (!silent) toast(`${t("common.loadFailed")}: ${error.message}`);
    throw error;
  }
}

function renderLogs() {
  const filter = ($("#log-filter").value || "").trim().toLowerCase();
  const lines = filter ? STATE.logs.filter((line) => line.toLowerCase().includes(filter)) : STATE.logs;
  $("#logs-view").textContent = lines.length ? lines.join("\n") : t("common.noData");
  $("#logs-pause").textContent = STATE.logsPaused ? t("common.resume") : t("common.pause");
}

function toggleLogs() {
  STATE.logsPaused = !STATE.logsPaused;
  renderLogs();
}

function renderOverviewSchedules() {
  const items = STATE.schedules.filter((schedule) => !schedule.completed).slice(0, 4);
  $("#overview-schedules").innerHTML = items.length ? items.map((schedule) => `
    <article class="data-item">
      <strong>${escapeHTML(schedule.title || t("common.unknown"))}</strong>
      <p class="body-copy">${escapeHTML(formatDate(schedule.datetime))}</p>
    </article>
  `).join("") : emptyState(t("common.noData"));
}

function renderOverviewConversation() {
  const items = STATE.conversations.slice(-4).reverse();
  $("#overview-conversation").innerHTML = items.length ? items.map((item) => {
    const normalized = normalizeConversation(item);
    return `
      <article class="data-item">
        <strong>${escapeHTML(roleLabel(normalized.role))}</strong>
        <p>${escapeHTML(truncate(normalized.content, 88))}</p>
      </article>
    `;
  }).join("") : emptyState(t("common.noData"));
}

function renderOverviewLogs() {
  const items = STATE.logs.slice(-4).reverse();
  $("#overview-logs").innerHTML = items.length ? items.map((line) => `
    <article class="data-item">
      <p>${escapeHTML(truncate(line, 110))}</p>
    </article>
  `).join("") : emptyState(t("common.noData"));
}

function renderStatus() {
  const status = STATE.status || {};
  const diagnostics = STATE.diagnostics || {};
  const connection = diagnostics.connection || {};
  const stt = diagnostics.stt || {};
  const runtime = diagnostics.runtime || {};
  const mode = status.mode || "agent";
  const emotion = status.emotion || "neutral";
  const conversationCount = Number(status.conversation_count || 0);

  $("#mode-chip").textContent = `${uiLabel("mode")} · ${modeLabel(mode)}`;
  $("#emotion-chip").textContent = `${uiLabel("emotion")} · ${emotionLabel(emotion)}`;
  $("#conversation-chip").textContent = `${formatNumber(conversationCount)} ${uiLabel("turns")}`;
  $("#sidebar-summary").textContent = sidebarSummary(status, connection);

  $("#hero-headline").textContent = heroHeadline();
  $("#hero-description").textContent = heroDescription(status, connection);
  $("#hero-note").textContent = heroNote();

  $("#metric-mode").textContent = modeLabel(mode);
  $("#metric-emotion").textContent = emotionLabel(emotion);
  $("#metric-conversation").textContent = formatNumber(conversationCount);
  $("#metric-connection").textContent = connection.connected ? transportLabel(connection.current_transport) : t("common.disconnected");

  /* ── Top metrics bar ── */
  const warmup = runtime.warmup || {};
  const barStt = $("#bar-stt .bar-metric-value");
  const barLlm = $("#bar-llm .bar-metric-value");
  const barConn = $("#bar-connection .bar-metric-value");
  const barMode = $("#bar-mode .bar-metric-value");
  if (barStt) { barStt.textContent = warmup.stt_ready ? "Ready" : "—"; barStt.className = "bar-metric-value" + (warmup.stt_ready ? "" : " warn"); }
  if (barLlm) { barLlm.textContent = warmup.tts_ready ? "Ready" : "—"; barLlm.className = "bar-metric-value" + (warmup.tts_ready ? "" : " warn"); }
  if (barConn) { barConn.textContent = connection.connected ? transportLabel(connection.current_transport) : "—"; barConn.className = "bar-metric-value" + (connection.connected ? "" : " error"); }
  if (barMode) { barMode.textContent = modeLabel(mode); }
}

function sidebarSummary(status, connection) {
  const proactive = status.proactive || {};
  if (connection.connected) {
    return `${transportLabel(connection.current_transport)} · ${connection.current_endpoint || t("common.connected")}`;
  }
  if (proactive && proactive.sleep_mode) {
    return localePhrase(
      `Sleep until ${formatDate(proactive.sleep_until)}`,
      `${formatDate(proactive.sleep_until)}까지 수면`,
      `${formatDate(proactive.sleep_until)} までスリープ`,
      `休眠至 ${formatDate(proactive.sleep_until)}`
    );
  }
  return t("brand.body");
}

function heroHeadline() {
  const mode = STATE.status?.mode || STATE.diagnostics?.mode || "agent";
  const connection = STATE.diagnostics?.connection || {};
  if (mode === "robot") return localePhrase("Robot mode is live", "로봇 모드가 동작 중입니다", "ロボットモードが動作中です", "机器人模式正在运行");
  if (connection.connected) return localePhrase("Ready for the next turn", "다음 대화를 받을 준비가 됐습니다", "次の会話の準備ができています", "已准备好接收下一轮对话");
  return localePhrase("Waiting for the device", "디바이스 연결을 기다리고 있습니다", "デバイス接続を待っています", "正在等待设备连接");
}

function heroDescription(status, connection) {
  const diagnostics = STATE.diagnostics || {};
  const stt = diagnostics.stt || {};
  if (connection.connected) {
    return localePhrase(
      `Current transport is ${transportLabel(connection.current_transport)} and STT is configured for ${stt.configured_device || t("common.unknown")}.`,
      `현재 ${transportLabel(connection.current_transport)} 경로로 연결되어 있고, STT는 ${stt.configured_device || t("common.unknown")} 기준으로 설정되어 있습니다.`,
      `現在の接続は ${transportLabel(connection.current_transport)} で、STT は ${stt.configured_device || t("common.unknown")} 基準で設定されています。`,
      `当前通过 ${transportLabel(connection.current_transport)} 连接，STT 已按 ${stt.configured_device || t("common.unknown")} 配置。`
    );
  }
  if (status.mode === "robot") {
    return localePhrase(
      "Servo and display actions are routed through the companion controller.",
      "서보와 디스플레이 동작이 컴패니언 컨트롤러를 통해 전달됩니다.",
      "サーボとディスプレイの動作はコンパニオンコントローラー経由で送信されます。",
      "伺服和显示操作通过伴侣控制器路由。"
    );
  }
  return localePhrase(
    "Connect the Atom Echo via USB or Wi-Fi to start a voice session.",
    "Atom Echo를 USB 또는 Wi-Fi로 연결하면 음성 세션이 시작됩니다.",
    "Atom Echo を USB または Wi-Fi で接続すると音声セッションが開始されます。",
    "通过 USB 或 Wi-Fi 连接 Atom Echo 以开始语音会话。"
  );
}

function heroNote() {
  const warmup = STATE.diagnostics?.runtime?.warmup || {};
  const connection = STATE.diagnostics?.connection || {};
  const parts = [
    warmup.stt_ready ? uiLabel("sttReady") : uiLabel("sttWaiting"),
    warmup.tts_ready ? uiLabel("ttsReady") : uiLabel("ttsWaiting"),
    connection.last_connected_at ? formatDate(connection.last_connected_at) : t("common.noData"),
  ];
  return parts.join(" · ");
}

function saveToken() {
  STATE.token = $("#auth-token").value.trim();
  if (STATE.token) {
    localStorage.setItem("ccoli.authToken", STATE.token);
  } else {
    localStorage.removeItem("ccoli.authToken");
  }
  clearPrivateView();
  toast(t("common.tokenSaved"));
  connectWs(true);
  refreshAll(true);
}

function clearToken() {
  STATE.token = "";
  $("#auth-token").value = "";
  localStorage.removeItem("ccoli.authToken");
  clearPrivateView();
  toast(t("common.tokenCleared"));
  connectWs(true);
  refreshAll(true);
}

function clearPrivateView() {
  STATE.authGeneration += 1;
  STATE.status = null;
  STATE.diagnostics = null;
  STATE.integrations = {};
  STATE.integrationHealth = {};
  STATE.memoryFiles = [];
  STATE.memoryFile = "Soul.md";
  STATE.conversations = [];
  STATE.schedules = [];
  STATE.logs = [];
  STATE.chat = [];
  STATE.configSnapshot = null;
  STATE.lastChatSignature = "";
  localStorage.removeItem("ccoli.activeMemory");

  $("#memory-editor").value = "";
  $("#memory-title").textContent = "";
  $("#memory-meta").textContent = "";
  $("#speaker-filter").innerHTML = `<option value="">${escapeHTML(t("conversation.filters.allSpeakers"))}</option>`;
  $("#speaker-filter").value = "";
  $("#chat-input").value = "";
  $("#chat-speaker").value = "web_user";
  $("#schedule-title").value = "";
  $("#schedule-description").value = "";
  $("#schedule-datetime").value = "";
  $("#log-filter").value = "";
  $("#stt-device").value = "";
  $("#stt-model-size").value = "";
  $("#connection-mode").value = "";
  renderAll();
}

function connectWs(force = false) {
  if (force) {
    clearWsTimers();
    STATE.wsAuthBlocked = false;
    const previous = STATE.ws;
    STATE.ws = null;
    try {
      if (previous) previous.close();
    } catch (error) {
      console.warn(error);
    }
  }

  if (STATE.wsAuthBlocked) return;
  if (STATE.ws && (STATE.ws.readyState === WebSocket.OPEN || STATE.ws.readyState === WebSocket.CONNECTING)) return;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  wsState(false, localePhrase("Connecting live...", "실시간 연결 중...", "ライブ接続中...", "正在连接实时流..."));

  let socket;
  try {
    socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    STATE.ws = socket;
  } catch (error) {
    wsState(false, localePhrase("Live connection failed", "실시간 연결 실패", "ライブ接続失敗", "实时连接失败"));
    toast(`${t("common.actionFailed")}: ${error.message}`);
    retryWs();
    return;
  }

  socket.addEventListener("open", () => {
    if (STATE.ws !== socket) return;
    try {
      socket.send(JSON.stringify({ event: "authenticate", token: STATE.token }));
    } catch (error) {
      socket.close();
      return;
    }
    wsState(true, localePhrase("Live connected", "실시간 연결됨", "ライブ接続済み", "实时连接成功"));
    clearWsTimers();
    STATE.wsHeartbeat = window.setInterval(() => {
      if (STATE.ws === socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 20000);
  });

  socket.addEventListener("message", (event) => {
    if (STATE.ws !== socket) return;
    try {
      handleWs(JSON.parse(event.data));
    } catch (error) {
      console.warn("Invalid websocket payload", error);
    }
  });

  socket.addEventListener("close", (event) => {
    if (STATE.ws !== socket) return;
    STATE.ws = null;
    clearWsTimers();
    if (event.code === 4401) {
      STATE.wsAuthBlocked = true;
      const guidance = localePhrase(
        "Live access denied. Enter the dashboard token in Advanced and save it.",
        "실시간 접근이 거부됐어요. 고급 설정에서 대시보드 토큰을 입력하고 저장하세요.",
        "ライブ接続が拒否されました。詳細設定でトークンを入力して保存してください。",
        "实时连接被拒绝。请在高级设置中输入并保存令牌。"
      );
      wsState(false, guidance);
      toast(guidance);
      return;
    }
    wsState(false, localePhrase("Reconnecting live...", "실시간 재연결 대기 중", "ライブ再接続待機中", "等待重新连接实时流"));
    retryWs();
  });

  socket.addEventListener("error", () => {
    if (STATE.ws !== socket) return;
    wsState(false, localePhrase("Live connection unstable", "실시간 연결 불안정", "ライブ接続が不安定です", "实时连接不稳定"));
  });
}

function handleWs(payload) {
  if (!payload || typeof payload !== "object") return;
  if (payload.event === "emotion_change") {
    STATE.status = { ...(STATE.status || {}), emotion: payload.emotion };
    renderStatus();
    return;
  }
  if (payload.event === "status_update") {
    STATE.status = { ...(STATE.status || {}), ...payload };
    renderStatus();
    return;
  }
  if (payload.event === "log" && payload.line) {
    STATE.logs.push(payload.line);
    STATE.logs = STATE.logs.slice(-500);
    if (!STATE.logsPaused) renderLogs();
    renderOverviewLogs();
    return;
  }
  if (payload.event === "chat_response") {
    const signature = `${payload.speaker_id || ""}::${payload.text || ""}::${payload.response || ""}`;
    if (signature === STATE.lastChatSignature) return;
    STATE.lastChatSignature = signature;
    if (payload.text) appendChat("user", payload.text, { speaker: payload.speaker_id || "web_user" });
    if (payload.response) appendChat("assistant", payload.response, { emotion: payload.emotion, intent: payload.intent });
  }
}

function wsState(live, label) {
  $("#ws-dot").classList.toggle("live", live);
  $("#ws-label").textContent = label;
}

function retryWs() {
  if (STATE.wsAuthBlocked) return;
  if (!STATE.wsRetry) {
    STATE.wsRetry = window.setTimeout(() => {
      STATE.wsRetry = null;
      connectWs();
    }, 3000);
  }
}

function clearWsTimers() {
  if (STATE.wsHeartbeat) {
    window.clearInterval(STATE.wsHeartbeat);
    STATE.wsHeartbeat = null;
  }
  if (STATE.wsRetry) {
    window.clearTimeout(STATE.wsRetry);
    STATE.wsRetry = null;
  }
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  $("#toasts").appendChild(node);
  window.setTimeout(() => {
    node.classList.add("removing");
    window.setTimeout(() => node.remove(), 200);
  }, 2400);
}

function normalizeConversation(item) {
  if (typeof item === "string") return { role: "user", content: item, timestamp: "", emotion: "" };
  return {
    role: item?.role || "system",
    content: item?.content || item?.text || JSON.stringify(item || ""),
    timestamp: item?.timestamp || item?.created_at || "",
    emotion: item?.emotion || "",
  };
}

function roleLabel(role) {
  const labels = {
    user: localePhrase("User", "사용자", "ユーザー", "用户"),
    assistant: "ccoli",
    system: localePhrase("System", "시스템", "システム", "系统"),
  };
  return labels[role] || role;
}

function modeLabel(mode) {
  const labels = {
    agent: localePhrase("Agent", "에이전트", "エージェント", "代理模式"),
    robot: localePhrase("Robot", "로봇", "ロボット", "机器人"),
  };
  return labels[mode] || mode || t("common.unknown");
}

function transportLabel(transport) {
  const labels = {
    auto: localePhrase("Auto", "자동", "自動", "自动"),
    wired: localePhrase("Wired", "유선", "有線", "有线"),
    wifi: "Wi-Fi",
  };
  return labels[transport] || transport || t("common.unknown");
}

function emotionLabel(emotion) {
  const labels = {
    neutral: localePhrase("Neutral", "차분함", "ニュートラル", "平静"),
    happy: localePhrase("Happy", "기쁨", "喜び", "愉快"),
    excited: localePhrase("Excited", "들뜸", "高揚", "兴奋"),
    calm: localePhrase("Calm", "안정", "落ち着き", "平稳"),
    sad: localePhrase("Sad", "가라앉음", "悲しみ", "低落"),
    angry: localePhrase("Angry", "예민함", "怒り", "愤怒"),
    surprised: localePhrase("Surprised", "놀람", "驚き", "惊讶"),
    worried: localePhrase("Worried", "걱정", "心配", "担忧"),
  };
  return labels[emotion] || emotion || t("common.unknown");
}

function localePhrase(en, ko, ja, zh) {
  return { en, ko, ja, zh }[STATE.locale] || en;
}

function uiLabel(key) {
  const labels = {
    mode: localePhrase("Mode", "모드", "モード", "模式"),
    emotion: localePhrase("Emotion", "감정", "感情", "情绪"),
    turns: localePhrase("turns", "회", "件", "轮"),
    warmup: localePhrase("Warmup", "워밍업", "ウォームアップ", "预热"),
    llm: "LLM",
    connection: localePhrase("Connection", "연결", "接続", "连接"),
    modelSize: localePhrase("Model size", "모델 크기", "モデルサイズ", "模型大小"),
    configuredDevice: localePhrase("Configured device", "설정 디바이스", "設定デバイス", "配置设备"),
    resolvedOrder: localePhrase("Resolved order", "해결 순서", "解決順序", "解析顺序"),
    deviceInUse: localePhrase("Device in use", "사용 중 디바이스", "使用中デバイス", "当前设备"),
    language: localePhrase("Language", "언어", "言語", "语言"),
    runtimeNotes: localePhrase("Runtime notes", "런타임 메모", "ランタイムメモ", "运行时说明"),
    priority: localePhrase("Priority", "우선순위", "優先順位", "优先级"),
    connected: localePhrase("Connected", "연결 여부", "接続状態", "连接状态"),
    currentTransport: localePhrase("Current transport", "현재 연결 경로", "現在の経路", "当前链路"),
    endpoint: localePhrase("Endpoint", "엔드포인트", "エンドポイント", "端点"),
    lastConnected: localePhrase("Last connected", "마지막 연결 시각", "最終接続", "最近连接时间"),
    chars: localePhrase("chars", "자", "文字", "字"),
    minutes: localePhrase("min", "분", "分", "分钟"),
    sttReady: localePhrase("STT ready", "STT 준비 완료", "STT 準備完了", "STT 已就绪"),
    sttWaiting: localePhrase("STT waiting", "STT 대기 중", "STT 待機中", "STT 等待中"),
    ttsReady: localePhrase("TTS ready", "TTS 준비 완료", "TTS 準備完了", "TTS 已就绪"),
    ttsWaiting: localePhrase("TTS waiting", "TTS 대기 중", "TTS 待機中", "TTS 等待中"),
  };
  return labels[key] || key;
}

function warmupSummary(warmup) {
  const stt = warmup.stt_ready ? uiLabel("sttReady") : uiLabel("sttWaiting");
  const tts = warmup.tts_ready ? uiLabel("ttsReady") : uiLabel("ttsWaiting");
  return `${stt} · ${tts}`;
}

function yesNo(value) {
  return value ? t("common.yes") : t("common.no");
}

function arrayOrFallback(value) {
  return Array.isArray(value) && value.length ? value.join(" > ") : t("common.noData");
}

function emptyState(text) {
  return `<div class="empty-state">${escapeHTML(text)}</div>`;
}

function formatDate(value) {
  if (!value) return t("common.unknown");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(uiLocale(), { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatNumber(value) {
  return new Intl.NumberFormat(uiLocale()).format(Number(value || 0));
}

function truncate(value, maxLength) {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function seedDate() {
  const date = new Date();
  date.setMinutes(0, 0, 0);
  date.setHours(date.getHours() + 1);
  $("#schedule-datetime").value = localDate(date);
}

function localDate(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    "-",
    pad(date.getMonth() + 1),
    "-",
    pad(date.getDate()),
    "T",
    pad(date.getHours()),
    ":",
    pad(date.getMinutes()),
  ].join("");
}

function confirmMessage(type) {
  if (type === "conversation") {
    return localePhrase(
      "Clear the conversation history?",
      "대화 히스토리를 비울까요?",
      "会話履歴を削除しますか？",
      "要清空对话历史吗？"
    );
  }
  return localePhrase(
    "Delete this schedule?",
    "이 일정을 삭제할까요?",
    "この予定を削除しますか？",
    "要删除这个日程吗？"
  );
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
