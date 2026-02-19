package models

import (
	"strings"
	"time"

	"gorm.io/datatypes"
	"gorm.io/gorm"
)

const (
	ManagerStatusActive   = "active"
	ManagerStatusExpired  = "expired"
	ManagerStatusDisabled = "disabled"

	UserStatusActive   = "active"
	UserStatusExpired  = "expired"
	UserStatusDisabled = "disabled"

	UserTypeDaily  = "daily"
	UserTypeDuiyi  = "duiyi"
	UserTypeShuaka = "shuaka"

	CodeStatusUnused  = "unused"
	CodeStatusUsed    = "used"
	CodeStatusRevoked = "revoked"

	JobStatusPending  = "pending"
	JobStatusLeased   = "leased"
	JobStatusRunning  = "running"
	JobStatusSuccess  = "success"
	JobStatusFailed   = "failed"
	JobStatusRequeued = "timeout_requeued"

	ActorTypeSuper   = "super"
	ActorTypeManager = "manager"
	ActorTypeUser    = "user"
	ActorTypeAgent   = "agent"

	AccountStatusActive    = "active"
	AccountStatusInvalid   = "invalid"
	AccountStatusCangbaoge = "cangbaoge"

	ProgressInit = "init"
	ProgressOk   = "ok"
)

type SuperAdmin struct {
	ID           uint      `gorm:"primaryKey"`
	Username     string    `gorm:"size:64;not null;uniqueIndex"`
	PasswordHash string    `gorm:"size:255;not null"`
	CreatedAt    time.Time `gorm:"not null"`
	UpdatedAt    time.Time `gorm:"not null"`
}

type Manager struct {
	ID           uint       `gorm:"primaryKey"`
	Username     string     `gorm:"size:64;not null;uniqueIndex"`
	PasswordHash string     `gorm:"size:255;not null"`
	Status       string     `gorm:"size:20;not null;default:expired;index"`
	ExpiresAt    *time.Time `gorm:"index"`
	CreatedAt    time.Time  `gorm:"not null"`
	UpdatedAt    time.Time  `gorm:"not null"`
}

type ManagerRenewalKey struct {
	ID                    uint   `gorm:"primaryKey"`
	Code                  string `gorm:"size:64;not null;uniqueIndex"`
	DurationDays          int    `gorm:"not null"`
	Status                string `gorm:"size:20;not null;default:unused;index"`
	UsedByManagerID       *uint  `gorm:"index"`
	UsedAt                *time.Time
	CreatedBySuperAdminID uint      `gorm:"not null;index"`
	CreatedAt             time.Time `gorm:"not null"`
}

type User struct {
	ID        uint              `gorm:"primaryKey"`
	AccountNo string            `gorm:"size:64;not null;uniqueIndex"`
	ManagerID uint              `gorm:"not null;index"`
	UserType  string            `gorm:"size:20;not null;default:daily;index"`
	Status    string            `gorm:"size:20;not null;default:expired;index"`
	ExpiresAt *time.Time        `gorm:"index"`
	Assets          datatypes.JSONMap `gorm:"type:jsonb;not null;default:'{}'"`
	LoginID         string            `gorm:"column:login_id;size:64"`
	Progress        string            `gorm:"column:progress;size:20;default:ok"`
	AccountStatus   string            `gorm:"column:account_status;size:20;default:active"`
	CurrentTask     string            `gorm:"column:current_task;size:64"`
	LineupConfig    datatypes.JSON    `gorm:"column:lineup_config;type:jsonb"`
	ShikamiConfig   datatypes.JSON    `gorm:"column:shikigami_config;type:jsonb"`
	ExploreProgress datatypes.JSON    `gorm:"column:explore_progress;type:jsonb"`
	Remark          string            `gorm:"column:remark;size:500"`
	CreatedBy       string            `gorm:"size:30;not null"`
	CreatedAt       time.Time         `gorm:"not null"`
	UpdatedAt       time.Time         `gorm:"not null"`
}

type UserToken struct {
	ID         uint      `gorm:"primaryKey"`
	UserID     uint      `gorm:"not null;index"`
	TokenHash  string    `gorm:"size:64;not null;uniqueIndex"`
	ExpiresAt  time.Time `gorm:"not null;index"`
	RevokedAt  *time.Time
	CreatedAt  time.Time `gorm:"not null"`
	LastUsedAt *time.Time
	DeviceInfo string `gorm:"size:255"`
}

type UserActivationCode struct {
	ID           uint   `gorm:"primaryKey"`
	ManagerID    uint   `gorm:"not null;index"`
	UserType     string `gorm:"size:20;not null;default:daily;index"`
	Code         string `gorm:"size:64;not null;uniqueIndex"`
	DurationDays int    `gorm:"not null"`
	Status       string `gorm:"size:20;not null;default:unused;index"`
	UsedByUserID *uint  `gorm:"index"`
	UsedAt       *time.Time
	CreatedAt    time.Time `gorm:"not null"`
}

type UserTaskConfig struct {
	ID         uint              `gorm:"primaryKey"`
	UserID     uint              `gorm:"not null;uniqueIndex"`
	TaskConfig datatypes.JSONMap `gorm:"type:jsonb;not null;default:'{}'"`
	UpdatedAt  time.Time         `gorm:"not null"`
	Version    int               `gorm:"not null;default:1"`
}

type TaskJob struct {
	ID           uint              `gorm:"primaryKey"`
	ManagerID    uint              `gorm:"not null;index:idx_task_jobs_manager_status_scheduled,priority:1"`
	UserID       uint              `gorm:"not null;index"`
	TaskType     string            `gorm:"size:64;not null"`
	Payload      datatypes.JSONMap `gorm:"type:jsonb;not null;default:'{}'"`
	Priority     int               `gorm:"not null;default:0"`
	ScheduledAt  time.Time         `gorm:"not null;index:idx_task_jobs_manager_status_scheduled,priority:3"`
	Status       string            `gorm:"size:24;not null;default:pending;index:idx_task_jobs_manager_status_scheduled,priority:2"`
	LeasedByNode string            `gorm:"size:128;index"`
	LeaseUntil   *time.Time        `gorm:"index"`
	Attempts     int               `gorm:"not null;default:0"`
	MaxAttempts  int               `gorm:"not null;default:3"`
	CreatedAt    time.Time         `gorm:"not null"`
	UpdatedAt    time.Time         `gorm:"not null"`
}

type TaskJobEvent struct {
	ID        uint      `gorm:"primaryKey"`
	JobID     uint      `gorm:"not null;index"`
	EventType string    `gorm:"size:24;not null;index"`
	Message   string    `gorm:"type:text"`
	ErrorCode string    `gorm:"size:64"`
	EventAt   time.Time `gorm:"not null;index"`
}

type AgentNode struct {
	ID            uint      `gorm:"primaryKey"`
	ManagerID     uint      `gorm:"not null;index"`
	NodeID        string    `gorm:"size:128;not null;uniqueIndex"`
	LastHeartbeat time.Time `gorm:"not null;index"`
	Status        string    `gorm:"size:20;not null;default:online"`
	Version       string    `gorm:"size:64"`
	CreatedAt     time.Time `gorm:"not null"`
	UpdatedAt     time.Time `gorm:"not null"`
}

type AuditLog struct {
	ID         uint              `gorm:"primaryKey"`
	ActorType  string            `gorm:"size:20;not null;index"`
	ActorID    uint              `gorm:"not null;index"`
	Action     string            `gorm:"size:64;not null;index"`
	TargetType string            `gorm:"size:40;not null"`
	TargetID   uint              `gorm:"not null"`
	Detail     datatypes.JSONMap `gorm:"type:jsonb;not null;default:'{}'"`
	IP         string            `gorm:"size:64"`
	CreatedAt  time.Time         `gorm:"not null;index"`
}

type UserRestConfig struct {
	ID           uint      `gorm:"primaryKey"`
	UserID       uint      `gorm:"uniqueIndex;not null"`
	Enabled      bool      `gorm:"default:false"`
	Mode         string    `gorm:"size:20;default:random"`
	RestStart    string    `gorm:"size:10"`
	RestDuration int
	CreatedAt    time.Time `gorm:"not null"`
	UpdatedAt    time.Time `gorm:"not null"`
}

type CoopAccount struct {
	ID         uint       `gorm:"primaryKey"`
	ManagerID  uint       `gorm:"index;not null"`
	LoginID    string     `gorm:"size:64;not null"`
	Status     string     `gorm:"size:20;default:active"`
	ExpireDate *time.Time
	Note       string     `gorm:"size:500"`
	CreatedAt  time.Time  `gorm:"not null"`
	UpdatedAt  time.Time  `gorm:"not null"`
}

type CoopPool struct {
	ID            uint       `gorm:"primaryKey"`
	OwnerUserID   uint       `gorm:"index"`
	CoopAccountID uint       `gorm:"index"`
	UsedCount     int        `gorm:"default:0"`
	LastUsedAt    *time.Time
	CreatedAt     time.Time  `gorm:"not null"`
	UpdatedAt     time.Time  `gorm:"not null"`
}

type CoopWindow struct {
	ID            uint      `gorm:"primaryKey"`
	CoopAccountID uint      `gorm:"index"`
	WindowDate    time.Time `gorm:"type:date"`
	Slot          int
	UsedCount     int       `gorm:"default:0"`
	CreatedAt     time.Time `gorm:"not null"`
	UpdatedAt     time.Time `gorm:"not null"`
}

type UserLog struct {
	ID      uint      `gorm:"primaryKey"`
	UserID  uint      `gorm:"index;not null"`
	LogType string    `gorm:"size:64"`
	Level   string    `gorm:"size:20;default:info"`
	Message string    `gorm:"type:text"`
	Ts      time.Time `gorm:"index"`
}

func AutoMigrate(db *gorm.DB) error {
	return db.AutoMigrate(
		&SuperAdmin{},
		&Manager{},
		&ManagerRenewalKey{},
		&User{},
		&UserToken{},
		&UserActivationCode{},
		&UserTaskConfig{},
		&TaskJob{},
		&TaskJobEvent{},
		&AgentNode{},
		&AuditLog{},
		&UserRestConfig{},
		&CoopAccount{},
		&CoopPool{},
		&CoopWindow{},
		&UserLog{},
	)
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

func IsValidUserType(value string) bool {
	normalized := NormalizeUserType(value)
	raw := strings.ToLower(strings.TrimSpace(value))
	return raw == normalized
}
