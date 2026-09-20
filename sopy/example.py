from systemone import SystemOne

with open("systemone.apikey", "r", encoding="utf-8") as rf:
    api_key = rf.read().strip()

so = SystemOne()
so.use("typesafe", api_key=api_key)

so.state = "我的月度订阅被扣了两次款。能帮我核查一下这两笔付款吗？"

so.addq("Q0", "这属于资金问题吗？", "noul")
so.addq("Q1", "这属于哪一类反馈？", "choice", dict.fromkeys(["故障或错误", "功能建议", "账单问题", "使用求助", "正面反馈", "其他"], None))
so.addq("Q2", "该问题严重吗？", "score", ["忽略", "注意", "警告", "严重"])

so.run()
so.print_answers()