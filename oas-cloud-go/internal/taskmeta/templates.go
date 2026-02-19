package taskmeta

import (
	"fmt"
	"strings"
)

const (
	UserTypeDaily  = "daily"
	UserTypeDuiyi  = "duiyi"
	UserTypeShuaka = "shuaka"
)

var allTaskOrder = []string{
	"寄养",
	"悬赏",
	"弥助",
	"勾协",
	"探索突破",
	"结界卡合成",
	"加好友",
	"领取登录礼包",
	"领取邮件",
	"爬塔",
	"逢魔",
	"地鬼",
	"道馆",
	"寮商店",
	"领取寮金币",
	"每日一抽",
	"每周商店",
	"秘闻",
	"签到",
	"御魂",
	"每周分享",
	"召唤礼包",
	"领取饭盒酒壶",
	"斗技",
	"对弈竞猜",
	"起号_租借式神",
	"起号_领取奖励",
	"起号_新手任务",
	"起号_经验副本",
	"起号_领取锦囊",
	"起号_式神养成",
	"起号_升级饭盒",
	"领取成就奖励",
}

// daily task pool: aligned with local DEFAULT_TASK_CONFIG.
var dailyTaskOrder = []string{
	"寄养",
	"悬赏",
	"弥助",
	"勾协",
	"探索突破",
	"结界卡合成",
	"加好友",
	"领取登录礼包",
	"领取邮件",
	"爬塔",
	"逢魔",
	"地鬼",
	"道馆",
	"寮商店",
	"领取寮金币",
	"每日一抽",
	"每周商店",
	"秘闻",
	"签到",
	"御魂",
	"每周分享",
	"召唤礼包",
	"领取饭盒酒壶",
	"斗技",
	"对弈竞猜",
}

// shuaka task pool: aligned with local DEFAULT_INIT_TASK_CONFIG.
var shuakaTaskOrder = []string{
	"起号_租借式神",
	"起号_领取奖励",
	"起号_新手任务",
	"起号_经验副本",
	"起号_领取锦囊",
	"起号_式神养成",
	"起号_升级饭盒",
	"探索突破",
	"爬塔",
	"签到",
	"地鬼",
	"每周商店",
	"寮商店",
	"领取寮金币",
	"领取邮件",
	"加好友",
	"领取登录礼包",
	"每日一抽",
	"弥助",
	"领取成就奖励",
	"每周分享",
	"召唤礼包",
	"领取饭盒酒壶",
	"斗技",
	"对弈竞猜",
}

var duiyiTaskOrder = []string{
	"对弈竞猜",
}

var defaultTaskConfig = map[string]map[string]any{
	"寄养":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "interval_6h"},
	"悬赏":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"弥助":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"勾协":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"探索突破":    {"enabled": true, "sub_explore": true, "sub_tupo": true, "stamina_threshold": 1000, "difficulty": "normal", "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "interval_8h"},
	"结界卡合成":   {"enabled": true, "explore_count": 0, "next_time_rule": "daily_reset"},
	"加好友":     {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"领取登录礼包":  {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"领取邮件":    {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"爬塔":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"逢魔":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"地鬼":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"道馆":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"寮商店":     {"enabled": true, "next_time": "2020-01-01 00:00", "buy_heisui": true, "buy_lanpiao": true, "fail_delay": 30, "next_time_rule": "daily_reset"},
	"领取寮金币":   {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"每日一抽":    {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"每周商店":    {"enabled": true, "next_time": "2020-01-01 00:00", "buy_lanpiao": true, "buy_heidan": true, "buy_tili": true, "fail_delay": 30, "next_time_rule": "weekly_7d"},
	"秘闻":      {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "weekly_monday"},
	"签到":      {"enabled": false, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"御魂":      {"enabled": false, "run_count": 0, "remaining_count": 0, "unlocked_count": 0, "target_level": 10, "fail_delay": 2880, "next_time_rule": "on_demand"},
	"每周分享":    {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "weekly_7d"},
	"召唤礼包":    {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"领取饭盒酒壶":  {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"斗技":      {"enabled": false, "start_hour": 12, "end_hour": 23, "mode": "honor", "target_score": 2000, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "coop_window"},
	"对弈竞猜":    {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "interval_2h_window"},
	"起号_租借式神": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"起号_领取奖励": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"起号_新手任务": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"起号_经验副本": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"起号_领取锦囊": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"起号_式神养成": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"起号_升级饭盒": {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
	"领取成就奖励":  {"enabled": true, "next_time": "2020-01-01 00:00", "fail_delay": 30, "next_time_rule": "daily_reset"},
}

var defaultUserAssets = map[string]any{
	"level":       1,
	"stamina":     0,
	"gouyu":       0,
	"lanpiao":     0,
	"gold":        0,
	"gongxun":     0,
	"xunzhang":    0,
	"tupo_ticket": 0,
	"fanhe_level": 1,
	"jiuhu_level": 1,
	"liao_level":  0,
}

func UserTypes() []string {
	return []string{UserTypeDaily, UserTypeDuiyi, UserTypeShuaka}
}

func NormalizeUserType(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case UserTypeDaily:
		return UserTypeDaily
	case UserTypeDuiyi:
		return UserTypeDuiyi
	case UserTypeShuaka:
		return UserTypeShuaka
	default:
		return UserTypeDaily
	}
}

func TaskPools() map[string][]string {
	return map[string][]string{
		UserTypeDaily:  UserTypeTaskOrder(UserTypeDaily),
		UserTypeDuiyi:  UserTypeTaskOrder(UserTypeDuiyi),
		UserTypeShuaka: UserTypeTaskOrder(UserTypeShuaka),
	}
}

func UserTypeTaskOrder(userType string) []string {
	switch NormalizeUserType(userType) {
	case UserTypeDuiyi:
		return cloneStrings(duiyiTaskOrder)
	case UserTypeShuaka:
		return cloneStrings(shuakaTaskOrder)
	default:
		return cloneStrings(dailyTaskOrder)
	}
}

func DefaultTaskOrder() []string {
	return cloneStrings(allTaskOrder)
}

func BuildDefaultTaskConfig() map[string]any {
	return buildDefaultTaskConfigByOrder(allTaskOrder)
}

func BuildDefaultTaskConfigByType(userType string) map[string]any {
	return buildDefaultTaskConfigByOrder(UserTypeTaskOrder(userType))
}

func BuildDefaultUserAssets() map[string]any {
	return cloneMap(defaultUserAssets)
}

func IsTaskAllowedForType(taskName string, userType string) bool {
	_, ok := allowedTaskSet(userType)[taskName]
	return ok
}

func FilterTaskPatchByType(patch map[string]any, userType string) (map[string]any, error) {
	if patch == nil {
		return map[string]any{}, nil
	}
	allowed := allowedTaskSet(userType)
	filtered := map[string]any{}
	for taskName, value := range patch {
		if _, ok := allowed[taskName]; !ok {
			return nil, fmt.Errorf("task %s is not allowed for user type %s", taskName, NormalizeUserType(userType))
		}
		filtered[taskName] = value
	}
	return filtered, nil
}

func NormalizeTaskConfig(existing map[string]any) map[string]any {
	base := BuildDefaultTaskConfig()
	if existing == nil {
		return base
	}
	for taskName, taskConfig := range base {
		_, exists := existing[taskName]
		if exists {
			continue
		}
		taskMap, ok := taskConfig.(map[string]any)
		if !ok {
			continue
		}
		taskMap["enabled"] = false
		base[taskName] = taskMap
	}
	return deepMerge(base, existing)
}

func NormalizeTaskConfigByType(existing map[string]any, userType string) map[string]any {
	base := BuildDefaultTaskConfigByType(userType)
	if existing == nil {
		return base
	}
	allowed := allowedTaskSet(userType)
	filtered := map[string]any{}
	for taskName, value := range existing {
		if _, ok := allowed[taskName]; ok {
			filtered[taskName] = value
		}
	}
	for taskName, taskConfig := range base {
		if _, exists := filtered[taskName]; exists {
			continue
		}
		taskMap, ok := taskConfig.(map[string]any)
		if !ok {
			continue
		}
		taskMap["enabled"] = false
		base[taskName] = taskMap
	}
	return deepMerge(base, filtered)
}

func BuildTaskTemplateList() []map[string]any {
	return buildTaskTemplateListByOrder(allTaskOrder)
}

func BuildTaskTemplateListByType(userType string) []map[string]any {
	return buildTaskTemplateListByOrder(UserTypeTaskOrder(userType))
}

func buildDefaultTaskConfigByOrder(order []string) map[string]any {
	config := map[string]any{}
	for _, taskName := range order {
		src, ok := defaultTaskConfig[taskName]
		if !ok {
			continue
		}
		config[taskName] = cloneMap(src)
	}
	return config
}

func buildTaskTemplateListByOrder(order []string) []map[string]any {
	items := make([]map[string]any, 0, len(order))
	for _, taskName := range order {
		taskCfg, ok := defaultTaskConfig[taskName]
		if !ok {
			continue
		}
		items = append(items, map[string]any{
			"name":   taskName,
			"config": cloneMap(taskCfg),
		})
	}
	return items
}

func allowedTaskSet(userType string) map[string]struct{} {
	order := UserTypeTaskOrder(userType)
	items := make(map[string]struct{}, len(order))
	for _, taskName := range order {
		items[taskName] = struct{}{}
	}
	return items
}

func cloneStrings(items []string) []string {
	result := make([]string, 0, len(items))
	result = append(result, items...)
	return result
}

func cloneMap(source map[string]any) map[string]any {
	result := map[string]any{}
	for key, value := range source {
		switch typed := value.(type) {
		case map[string]any:
			result[key] = cloneMap(typed)
		case []any:
			newSlice := make([]any, 0, len(typed))
			for _, item := range typed {
				newSlice = append(newSlice, item)
			}
			result[key] = newSlice
		default:
			result[key] = typed
		}
	}
	return result
}

func deepMerge(base map[string]any, patch map[string]any) map[string]any {
	merged := map[string]any{}
	for key, value := range base {
		merged[key] = value
	}
	for key, value := range patch {
		existing, has := merged[key]
		if !has {
			merged[key] = value
			continue
		}
		existingMap, ok1 := existing.(map[string]any)
		patchMap, ok2 := value.(map[string]any)
		if ok1 && ok2 {
			merged[key] = deepMerge(existingMap, patchMap)
			continue
		}
		merged[key] = value
	}
	return merged
}

func ParseAssetInt(value any, fallback int) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case float32:
		return int(typed)
	default:
		return fallback
	}
}

func ValidateAssetKey(key string) error {
	if _, ok := defaultUserAssets[key]; !ok {
		return fmt.Errorf("unsupported asset key: %s", key)
	}
	return nil
}
