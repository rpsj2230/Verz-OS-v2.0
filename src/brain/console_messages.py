"""The words of the console's most-read pages, in every language this product ships.

`brain.locale.MESSAGES` holds the strings a Python function would otherwise return as English
prose. The console is a separate application whose pages drew their words from TSX constants, so an
install that offered Simplified Chinese was offered it in the setup wizard and nowhere a person
works. This is the catalogue those constants are looked up in: Ask, My workspace and Approvals,
which are the pages a person reads most, and the place the rest follow.

**The English is written where it is drawn, and this holds the same words again.** Each constant in
the console is `msg("<key>", "<English>")`: with nothing served, or with English chosen, the
English stands, so every page and every test that names a constant renders what it always did.
`tests/unit/test_console_messages.py` reads those calls out of the TSX and holds the English in them
to the English here, in both directions, so a sentence edited in one place and not the other is a
red build and not a screen that quietly says two things. Rejected: serving the English too and
having the console draw only from the served catalogue, which would make every console test
depend on a server and every page blank where the document fails to load. Rejected: generating
the console's constants from this module, which would put a generated file in a tree whose
constants tests import by name.

**Only the keys in `CONSOLE_KEYS` are served, for every enabled language.** A person may switch
language without a round trip, and the document is small: a hundred sentences in each language. A
key a page does not use is not sent, because the catalogue is a promise about what is drawn.

**There is no fallback, as `brain.locale` argues.** A key with no Chinese entry is a red build
through `brain.locale.catalogue_gaps`, run over this mapping by the same test.

Task ids: M35.1.1.1
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

#: Every sentence, keyed by `console.<page>.<name>` and then by language tag.
CONSOLE_MESSAGES: Final[Mapping[str, Mapping[str, str]]] = {
    "console.approvals.approvals_heading": {
        "en": "Approvals",
        "zh-Hans": "审批",
    },
    "console.approvals.approvals_lede": {
        "en": "Actions waiting for you to decide, soonest to lapse first. One nobody decides lapses, and nothing is done.",
        "zh-Hans": "等待你决定的操作，按失效时间从近到远排列。无人决定的审批会失效，且不会执行任何操作。",
    },
    "console.approvals.no_approvals": {
        "en": "Nothing is waiting for you.",
        "zh-Hans": "目前没有等待你处理的审批。",
    },
    "console.approvals.no_approvals_more": {
        "en": "An approval appears here when an agent asks before acting on something you may decide.",
        "zh-Hans": "当智能体在执行你可以决定的事项之前请求确认时，审批会出现在这里。",
    },
    "console.approvals.more_approvals": {
        "en": "There are more approvals than this page shows.",
        "zh-Hans": "审批数量超过本页可显示的范围。",
    },
    "console.approvals.approval_list_label": {
        "en": "Approvals waiting for you",
        "zh-Hans": "等待你处理的审批",
    },
    "console.approvals.filters_label": {
        "en": "Narrow the approvals",
        "zh-Hans": "筛选审批",
    },
    "console.approvals.reading_approvals": {
        "en": "Reading the approvals waiting for you.",
        "zh-Hans": "正在读取等待你处理的审批。",
    },
    "console.approvals.runs_as_label": {
        "en": "Runs as",
        "zh-Hans": "运行身份",
    },
    "console.approvals.raised_label": {
        "en": "Raised",
        "zh-Hans": "提出时间",
    },
    "console.approvals.lapses_label": {
        "en": "Lapses",
        "zh-Hans": "失效时间",
    },
    "console.approvals.open_on_its_own": {
        "en": "Open on its own",
        "zh-Hans": "单独打开",
    },
    "console.approvals.approve_label": {
        "en": "Approve",
        "zh-Hans": "批准",
    },
    "console.approvals.reject_label": {
        "en": "Reject",
        "zh-Hans": "拒绝",
    },
    "console.approvals.reason_label": {
        "en": "Reason for rejecting",
        "zh-Hans": "拒绝原因",
    },
    "console.approvals.no_reason_chosen": {
        "en": "Choose a reason",
        "zh-Hans": "请选择原因",
    },
    "console.approvals.approved_sentence": {
        "en": "Approved.",
        "zh-Hans": "已批准。",
    },
    "console.approvals.rejected_sentence": {
        "en": "Rejected.",
        "zh-Hans": "已拒绝。",
    },
    "console.approvals.take_over_label": {
        "en": "Take over",
        "zh-Hans": "接管",
    },
    "console.approvals.take_over_reason_label": {
        "en": "Reason for taking it over",
        "zh-Hans": "接管原因",
    },
    "console.approvals.taken_over_sentence": {
        "en": "Taken over. The agent will not do it; it is yours to do.",
        "zh-Hans": "已接管。智能体不会执行此事，需由你来完成。",
    },
    "console.approvals.take_over_question": {
        "en": "Take this over and do it yourself?",
        "zh-Hans": "接管此事并自己完成吗？",
    },
    "console.approvals.take_over_consequence": {
        "en": "The agent will not do it, and nothing it prepared is sent or changed. It is recorded as taken over, and three takeovers of the same kind of action inside a week hold this agent a step lower on it, so a person sees more of its work first.",
        "zh-Hans": "智能体不会执行此事，它已准备的内容也不会被发送或更改。此事会记录为已接管；一周内对同类操作接管三次，该智能体在此类操作上的权限将降低一级，使人能更多地先行查看其工作。",
    },
    "console.approvals.keep_it_label": {
        "en": "Keep it waiting",
        "zh-Hans": "保持等待",
    },
    "console.approvals.needs_two_sentence": {
        "en": "This cannot be taken back, so two different people approve it. Your approval is the first, and it runs only after a second person approves.",
        "zh-Hans": "此操作无法撤回，因此需要两位不同的人批准。你的批准是第一次，须待第二位批准后才会执行。",
    },
    "console.approvals.second_of_two_sentence": {
        "en": "This cannot be taken back, and one person has already approved it. Your approval is the second, and it runs when you give it.",
        "zh-Hans": "此操作无法撤回，且已有一人批准。你的批准是第二次，你批准后即执行。",
    },
    "console.approvals.approved_first_sentence": {
        "en": "Approved. Yours is the first approval of two, so it has not run and waits for a second person.",
        "zh-Hans": "已批准。你的批准是两次中的第一次，因此尚未执行，等待第二位批准。",
    },
    "console.approvals.reading_approval": {
        "en": "Reading the approval.",
        "zh-Hans": "正在读取该审批。",
    },
    "console.approvals.one_approval": {
        "en": "Approval",
        "zh-Hans": "审批",
    },
    "console.workspace.workspace_heading": {
        "en": "My workspace",
        "zh-Hans": "我的工作区",
    },
    "console.workspace.workspace_crumb": {
        "en": "Use › My workspace",
        "zh-Hans": "使用 › 我的工作区",
    },
    "console.workspace.workspace_lede": {
        "en": "What you asked, the agents you can call, what has been learnt about you, and what you keep. Everything on this page is yours or already visible to you, and it shows nothing your access would not already return in an answer.",
        "zh-Hans": "你提过的问题、你可以调用的智能体、系统了解到的关于你的信息，以及你所保管的内容。本页所有内容都属于你或本就对你可见，不会显示你的访问权限在回答中不会返回的任何内容。",
    },
    "console.workspace.reading_workspace": {
        "en": "Reading your workspace.",
        "zh-Hans": "正在读取你的工作区。",
    },
    "console.workspace.opens_on_the_member_grant": {
        "en": "This page opens for anybody holding the member grant, and for nobody else, whatever else they hold. If you expected to see it, ask your department administrator for it.",
        "zh-Hans": "持有成员权限的人可以打开本页，其他人无论持有何种权限都不能。若你应当看到本页，请向你所在部门的管理员申请。",
    },
    "console.workspace.no_agents": {
        "en": "There are no agents you can call.",
        "zh-Hans": "没有你可以调用的智能体。",
    },
    "console.workspace.no_ceiling": {
        "en": "No budget of your own is set.",
        "zh-Hans": "尚未为你设置个人预算。",
    },
    "console.workspace.nothing_learned": {
        "en": "Nothing learnt about you is shown.",
        "zh-Hans": "没有显示任何关于你的已了解信息。",
    },
    "console.workspace.no_items": {
        "en": "You do not look after any knowledge items.",
        "zh-Hans": "你没有负责任何知识条目。",
    },
    "console.workspace.more_items": {
        "en": "You look after more items than this page reads at once.",
        "zh-Hans": "你负责的条目多于本页一次可读取的数量。",
    },
    "console.workspace.edit_label": {
        "en": "Edit",
        "zh-Hans": "编辑",
    },
    "console.workspace.forget_label": {
        "en": "Forget",
        "zh-Hans": "忘记",
    },
    "console.workspace.save_label": {
        "en": "Save",
        "zh-Hans": "保存",
    },
    "console.workspace.cancel_label": {
        "en": "Cancel",
        "zh-Hans": "取消",
    },
    "console.workspace.keep_it": {
        "en": "Keep it",
        "zh-Hans": "保留",
    },
    "console.workspace.undo_all_label": {
        "en": "Undo all",
        "zh-Hans": "全部撤销",
    },
    "console.workspace.undo_all_question": {
        "en": "Forget everything learnt about you?",
        "zh-Hans": "忘记所有关于你的已了解信息吗？",
    },
    "console.workspace.undo_all_consequence": {
        "en": "Each memory stops being used in your answers at once. The records that they were learnt stay, and nothing you said in a conversation is deleted.",
        "zh-Hans": "每条记忆会立即停止用于你的回答。记录它们被了解过的内容会保留，你在对话中说过的内容不会被删除。",
    },
    "console.workspace.undone_all": {
        "en": "Everything learnt about you has been forgotten.",
        "zh-Hans": "所有关于你的已了解信息均已忘记。",
    },
    "console.workspace.what_it_should_say": {
        "en": "What it should say",
        "zh-Hans": "应该怎么说",
    },
    "console.workspace.what_it_takes": {
        "en": "One sentence about you, up to 280 characters, in your own words.",
        "zh-Hans": "一句关于你的话，最多 280 个字符，用你自己的话来写。",
    },
    "console.workspace.write_something": {
        "en": "Write what it should say before saving, or cancel to keep it.",
        "zh-Hans": "请先写下应有的内容再保存，或取消以保留原样。",
    },
    "console.workspace.forget_consequence": {
        "en": "It stops being used in your answers at once. The record that it was learnt stays, and if it replaced something earlier, the earlier one is used again.",
        "zh-Hans": "它会立即停止用于你的回答。记录它被了解过的内容会保留；若它取代了更早的一条，更早的一条会重新使用。",
    },
    "console.workspace.agents_caption": {
        "en": "Agents I can call",
        "zh-Hans": "我可以调用的智能体",
    },
    "console.workspace.items_caption": {
        "en": "Knowledge I own",
        "zh-Hans": "我负责的知识",
    },
    "console.workspace.learned_caption": {
        "en": "What it learned about me",
        "zh-Hans": "系统了解到的关于我的信息",
    },
    "console.workspace.evidence_caption": {
        "en": "What was noticed behind",
        "zh-Hans": "其背后注意到的内容",
    },
    "console.ask.ask_heading": {
        "en": "Ask",
        "zh-Hans": "提问",
    },
    "console.ask.ask_lede": {
        "en": "Ask a question. The answer is computed for what you are able to see.",
        "zh-Hans": "提出一个问题。回答会按你有权查看的内容生成。",
    },
    "console.ask.question_label": {
        "en": "Your question",
        "zh-Hans": "你的问题",
    },
    "console.ask.ask_label": {
        "en": "Ask",
        "zh-Hans": "提问",
    },
    "console.ask.progress_label": {
        "en": "While the answer is being made",
        "zh-Hans": "回答生成期间",
    },
    "console.ask.asking": {
        "en": "Asking.",
        "zh-Hans": "正在提问。",
    },
    "console.ask.based_on": {
        "en": "What this is based on",
        "zh-Hans": "依据",
    },
    "console.ask.nothing_asked_yet": {
        "en": "Nothing has been asked yet.",
        "zh-Hans": "尚未提出任何问题。",
    },
    "console.ask.skip_to_answer": {
        "en": "Skip to answer",
        "zh-Hans": "跳至回答",
    },
    "console.ask.answer_label": {
        "en": "Answer",
        "zh-Hans": "回答",
    },
    "console.ask.was_it_helpful": {
        "en": "Was this answer helpful?",
        "zh-Hans": "这个回答有帮助吗？",
    },
    "console.ask.copy_answer": {
        "en": "Copy answer",
        "zh-Hans": "复制回答",
    },
    "console.ask.answer_copied": {
        "en": "Copied.",
        "zh-Hans": "已复制。",
    },
    "console.ask.answer_not_copied": {
        "en": "Your browser did not allow copying. Select the answer and copy it by hand.",
        "zh-Hans": "你的浏览器不允许复制。请选中回答并手动复制。",
    },
    "console.ask.helpful": {
        "en": "Helpful",
        "zh-Hans": "有帮助",
    },
    "console.ask.not_helpful": {
        "en": "Not helpful",
        "zh-Hans": "没有帮助",
    },
    "console.ask.agent_label": {
        "en": "Answer as",
        "zh-Hans": "回答者",
    },
    "console.ask.any_agent": {
        "en": "Whichever agent suits the question",
        "zh-Hans": "由最适合该问题的智能体回答",
    },
    "console.ask.conversations_heading": {
        "en": "Your conversations",
        "zh-Hans": "你的对话",
    },
    "console.ask.search_conversations": {
        "en": "Search your questions",
        "zh-Hans": "搜索你的问题",
    },
    "console.ask.search_label": {
        "en": "Search",
        "zh-Hans": "搜索",
    },
    "console.ask.new_conversation": {
        "en": "Start a new conversation",
        "zh-Hans": "开始新对话",
    },
    "console.ask.continuing": {
        "en": "Your next question continues this conversation.",
        "zh-Hans": "你的下一个问题将接续此对话。",
    },
    "console.ask.nothing_found_in_conversations": {
        "en": "None of your questions holds those words.",
        "zh-Hans": "你的问题中没有包含这些词的内容。",
    },
    "console.ask.was_it_wrong": {
        "en": "Was this answer wrong?",
        "zh-Hans": "这个回答有误吗？",
    },
    "console.ask.what_is_right": {
        "en": "What is right? (optional)",
        "zh-Hans": "正确的是什么？（选填）",
    },
    "console.ask.what_is_right_hint": {
        "en": "Sent to whoever looks after the document this answer used. It changes nothing until they approve it.",
        "zh-Hans": "将发送给负责该回答所用文档的人。在他们批准之前不会改变任何内容。",
    },
    "console.ask.mark_wrong": {
        "en": "Mark it wrong",
        "zh-Hans": "标记为有误",
    },
    "console.ask.marked_wrong": {
        "en": "Marked. Your conversation now notes that this answer was wrong.",
        "zh-Hans": "已标记。你的对话现在会注明此回答有误。",
    },
    "console.ask.not_marked": {
        "en": "That could not be marked. Nothing was changed.",
        "zh-Hans": "无法标记。未作任何更改。",
    },
    "console.ask.export_conversation": {
        "en": "Export this conversation",
        "zh-Hans": "导出此对话",
    },
    "console.ask.not_exported": {
        "en": "That conversation could not be exported. Nothing was saved.",
        "zh-Hans": "无法导出该对话。未保存任何内容。",
    },
    "console.ask.kind_label": {
        "en": "Search only",
        "zh-Hans": "仅搜索",
    },
    "console.ask.any_kind": {
        "en": "Every kind of knowledge",
        "zh-Hans": "所有类型的知识",
    },
    "console.ask.start_legend": {
        "en": "How do you want to start?",
        "zh-Hans": "你想如何开始？",
    },
    "console.ask.start_task": {
        "en": "Start a task",
        "zh-Hans": "开始一项任务",
    },
    "console.ask.start_task_note": {
        "en": "Say what you need. An agent you may call is chosen for it, and it works with only what you are able to see.",
        "zh-Hans": "说明你需要什么。系统会为它选择一个你可以调用的智能体，且它只使用你有权查看的内容。",
    },
    "console.ask.talk_to_agent": {
        "en": "Talk to an agent",
        "zh-Hans": "与智能体对话",
    },
    "console.ask.talk_note": {
        "en": "Choose who you are talking to.",
        "zh-Hans": "选择你要与谁对话。",
    },
    "console.ask.starters_heading": {
        "en": "You could ask",
        "zh-Hans": "你可以问",
    },
    "console.ask.trial_needs_an_agent": {
        "en": "Choose the agent that will use it, then ask.",
        "zh-Hans": "请选择将使用它的智能体，然后提问。",
    },
    "console.ask.try_asking": {
        "en": "You could start with one of these.",
        "zh-Hans": "你可以从下面任选一个开始。",
    },
    "console.ask.from_your_data": {
        "en": "Or ask about what is connected for your department.",
        "zh-Hans": "或者就你所在部门已连接的内容提问。",
    },
    "console.ask.check_in": {
        "en": "Check the answer in",
        "zh-Hans": "在以下位置核对回答",
    },
    "console.shell.language_label": {
        "en": "Language",
        "zh-Hans": "语言",
    },
    "console.workspace.spent_of": {
        "en": "{spent} of {ceiling}, {percent}%",
        "zh-Hans": "已用 {spent}，共 {ceiling}，{percent}%",
    },
    "console.workspace.of_them_your_own": {
        "en": "{count} of them your own",
        "zh-Hans": "其中 {count} 个是你自己的",
    },
    "console.workspace.you_said_this": {
        "en": "You said this",
        "zh-Hans": "这是你说过的",
    },
    "console.workspace.inferred": {
        "en": "Inferred",
        "zh-Hans": "推断得出",
    },
    "console.ask.freshness_updated": {
        "en": "{text}, updated {date}",
        "zh-Hans": "{text}，更新于 {date}",
    },
    "console.ask.freshness_read": {
        "en": "{text}, read {date}",
        "zh-Hans": "{text}，读取于 {date}",
    },
}

#: The keys served to the console, in the order they are written here.
CONSOLE_KEYS: Final[tuple[str, ...]] = tuple(CONSOLE_MESSAGES)
