/* ============================================================
 * SystemOne Playground 配置
 * ============================================================ */

/* ---------- 默认选中（对应 models.json 的 Provider 键与模型 id） ---------- */
window.SO_CONFIG = {
  provider: "typesafe",
  model: "jev-latest"
};

/* ---------- 各项上限（自定义 Provider / Model 时使用） ---------- */
window.SO_LIMITS = {

  /* ---------- State ---------- */
  maxState: 10240,          // State 最大字符数（文本模式）

  /* ---------- Questions ---------- */
  maxQuestions: 16,        // 最多问题数量
  maxInstructions: 300,    // 每个问题的 instructions 最大字符数
  maxQuestionLabel: 40,    // 问题标签（Q1、Q2 …）最大字符数

  /* ---------- choice ---------- */
  maxChoiceOptions: 128,   // 选项数量上限（自定义模型时使用；已知模型取 models.json 的值）
  maxOptionName: 80,       // 单个选项名最大字符数
  maxOptionDesc: 200,      // 单个选项描述最大字符数

  /* ---------- score ---------- */
  minScoreLevels: 2,       // 等级数量下限
  maxScoreLevels: 10,      // 等级数量上限（自定义模型时使用；已知模型取 models.json 的值）
  maxLevelText: 200,       // 单个等级描述最大字符数

  /* ---------- 新增模型时的默认值 ---------- */
  contextWindow: 32000,    // 上下文长度

  /* ---------- 图片输入 ---------- */
  maxImages: 8,            // 单次最多附加的图片数量
  maxImageSize: 5242880,   // 单张图片最大字节数（5 MB）

  /* ---------- 结果列表 ---------- */
  resultLimit: 10,         // 默认显示的结果条数，超出的自动隐藏

  /* ---------- 历史记录 ---------- */
  historyLimit: 100        // 刷新时从 run-log.jsonl 恢复的历史运行条数（最多 500）

};
