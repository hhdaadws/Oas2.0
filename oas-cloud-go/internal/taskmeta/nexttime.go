package taskmeta

import "time"

// Beijing timezone: UTC+8
var bjLoc = time.FixedZone("Asia/Shanghai", 8*60*60)

// GetNextTimeRule returns the next_time_rule for a given task name.
// Returns empty string if the task is unknown.
func GetNextTimeRule(taskName string) string {
	cfg, ok := defaultTaskConfig[taskName]
	if !ok {
		return ""
	}
	rule, _ := cfg["next_time_rule"].(string)
	return rule
}

// CalcNextTime computes the next execution time based on rule and current UTC time.
// Returns zero time for "on_demand" or unknown rules.
func CalcNextTime(rule string, now time.Time) time.Time {
	bj := now.In(bjLoc)

	switch rule {
	case "daily_reset":
		// Tomorrow Beijing time 00:01
		tomorrow := time.Date(bj.Year(), bj.Month(), bj.Day()+1, 0, 1, 0, 0, bjLoc)
		return tomorrow.UTC()

	case "weekly_monday":
		// Next Monday Beijing time 00:01
		daysUntilMonday := (8 - int(bj.Weekday())) % 7
		if daysUntilMonday == 0 {
			daysUntilMonday = 7
		}
		nextMon := time.Date(bj.Year(), bj.Month(), bj.Day()+daysUntilMonday, 0, 1, 0, 0, bjLoc)
		return nextMon.UTC()

	case "interval_6h":
		return now.Add(6 * time.Hour)

	case "interval_8h":
		return now.Add(8 * time.Hour)

	case "interval_2h_window":
		// now + 2h, round to hour; if past 22:00 BJ, push to next day 10:00 BJ
		candidate := now.Add(2 * time.Hour)
		candidateBJ := candidate.In(bjLoc)
		candidateBJ = time.Date(candidateBJ.Year(), candidateBJ.Month(), candidateBJ.Day(), candidateBJ.Hour(), 0, 0, 0, bjLoc)
		if candidateBJ.Hour() >= 22 || candidateBJ.Hour() < 10 {
			// push to next day 10:00 BJ
			nextDay := time.Date(bj.Year(), bj.Month(), bj.Day()+1, 10, 0, 0, 0, bjLoc)
			if candidateBJ.Hour() >= 22 {
				// candidate is same day evening, next day is bj+1
				nextDay = time.Date(candidateBJ.Year(), candidateBJ.Month(), candidateBJ.Day()+1, 10, 0, 0, 0, bjLoc)
			}
			return nextDay.UTC()
		}
		return candidateBJ.UTC()

	case "coop_window":
		// Next Beijing time 18:00 or 21:00
		today18 := time.Date(bj.Year(), bj.Month(), bj.Day(), 18, 0, 0, 0, bjLoc)
		today21 := time.Date(bj.Year(), bj.Month(), bj.Day(), 21, 0, 0, 0, bjLoc)
		if now.Before(today18.UTC()) {
			return today18.UTC()
		}
		if now.Before(today21.UTC()) {
			return today21.UTC()
		}
		// Next day 18:00
		tomorrow18 := time.Date(bj.Year(), bj.Month(), bj.Day()+1, 18, 0, 0, 0, bjLoc)
		return tomorrow18.UTC()

	case "weekly_7d":
		return now.Add(7 * 24 * time.Hour)

	case "on_demand":
		return time.Time{}

	default:
		return time.Time{}
	}
}
