/* ============================================================
 * SystemOne Playground 配置
 * ============================================================ */

/* ---------- 默认模型（来自 models.json） ---------- */
window.SO_CONFIG = {
  provider: "typesafe",
  model: "jev-latest"      // model id
};

/* ---------- 各项上限 ---------- */
window.SO_LIMITS = {

  /* ---------- State ---------- */
  maxState: 32000,         // State 最大字符数（文本模式）

  /* ---------- 图片输入 ---------- */
  maxImages: 1,            // 单次最多附加的图片数量
  maxImageSize: 10485760,  // 单张图片最大字节数（10 MB）

  /* ---------- Questions ---------- */
  maxInstructions: 300,    // 单个问题的 instructions 最大字符数
  maxQuestionLabel: 20,    // 单个问题标签最大字符数

  /* ---------- choice ---------- */
  maxOptionName: 100,      // 单个选项名最大字符数
  maxOptionDesc: 300,      // 单个选项描述最大字符数

  /* ---------- score ---------- */
  minScoreLevels: 2,       // 等级数量下限
  maxLevelText: 200,       // 单个等级描述最大字符数

  /* ---------- 结果记录 ---------- */
  resultLimit: 5,          // 默认显示的结果条数
  historyLimit: 50         // 刷新时恢复的历史记录数（该值最多 500）

  /* ---------- 用于自定义 Provider / Model ---------- */
  contextWindow: 32000,    // 上下文长度
  maxQuestions: 64,        // 问题数量上限
  maxChoiceOptions: 26,    // 选项数量上限
  maxScoreLevels: 10,      // 等级数量上限

};
