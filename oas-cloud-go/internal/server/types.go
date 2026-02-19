package server

import "time"

type bootstrapInitRequest struct {
	Username string `json:"username" binding:"required,min=3,max=64"`
	Password string `json:"password" binding:"required,min=6,max=128"`
}

type loginRequest struct {
	Username string `json:"username" binding:"required,min=3,max=64"`
	Password string `json:"password" binding:"required,min=6,max=128"`
}

type createRenewalKeyRequest struct {
	DurationDays int `json:"duration_days" binding:"required,min=1,max=3650"`
}

type patchManagerStatusRequest struct {
	Status string `json:"status" binding:"required,oneof=active expired disabled"`
}

type patchCodeStatusRequest struct {
	Status string `json:"status" binding:"required,oneof=revoked"`
}

type managerRedeemKeyRequest struct {
	Code string `json:"code" binding:"required,min=6,max=64"`
}

type createActivationCodeRequest struct {
	DurationDays int    `json:"duration_days" binding:"required,min=1,max=3650"`
	UserType     string `json:"user_type" binding:"required,oneof=daily duiyi shuaka"`
}

type quickCreateUserRequest struct {
	DurationDays int    `json:"duration_days" binding:"required,min=1,max=3650"`
	UserType     string `json:"user_type" binding:"required,oneof=daily duiyi shuaka"`
}

type putTaskConfigRequest struct {
	TaskConfig map[string]any `json:"task_config" binding:"required"`
}

type managerPatchUserLifecycleRequest struct {
	ExpiresAt  string `json:"expires_at"`
	ExtendDays int    `json:"extend_days"`
	Status     string `json:"status"`
}

type superPatchManagerLifecycleRequest struct {
	ExpiresAt  string `json:"expires_at"`
	ExtendDays int    `json:"extend_days"`
	Status     string `json:"status"`
}

type putUserAssetsRequest struct {
	Assets map[string]any `json:"assets" binding:"required"`
}

type userRegisterByCodeRequest struct {
	Code string `json:"code" binding:"required,min=6,max=64"`
}

type userLoginRequest struct {
	AccountNo  string `json:"account_no" binding:"required,min=6,max=64"`
	DeviceInfo string `json:"device_info"`
}

type userRedeemCodeRequest struct {
	Code string `json:"code" binding:"required,min=6,max=64"`
}

type userLogoutRequest struct {
	All bool `json:"all"`
}

type agentLoginRequest struct {
	Username string `json:"username" binding:"required,min=3,max=64"`
	Password string `json:"password" binding:"required,min=6,max=128"`
	NodeID   string `json:"node_id" binding:"required,min=3,max=128"`
	Version  string `json:"version"`
}

type agentPollJobsRequest struct {
	NodeID       string `json:"node_id" binding:"required,min=3,max=128"`
	Limit        int    `json:"limit"`
	LeaseSeconds int    `json:"lease_seconds"`
}

type agentJobUpdateRequest struct {
	NodeID       string `json:"node_id" binding:"required,min=3,max=128"`
	Message      string `json:"message"`
	ErrorCode    string `json:"error_code"`
	LeaseSeconds int    `json:"lease_seconds"`
}

// ── Batch request types ───────────────────────────────

type batchUserLifecycleRequest struct {
	UserIDs    []uint `json:"user_ids" binding:"required,min=1,max=500"`
	ExpiresAt  string `json:"expires_at"`
	ExtendDays int    `json:"extend_days"`
	Status     string `json:"status"`
}

type batchUserAssetsRequest struct {
	UserIDs []uint         `json:"user_ids" binding:"required,min=1,max=500"`
	Assets  map[string]any `json:"assets" binding:"required"`
}

type batchCodeRevokeRequest struct {
	CodeIDs []uint `json:"code_ids" binding:"required,min=1,max=500"`
}

type batchManagerLifecycleRequest struct {
	ManagerIDs []uint `json:"manager_ids" binding:"required,min=1,max=200"`
	ExpiresAt  string `json:"expires_at"`
	ExtendDays int    `json:"extend_days"`
	Status     string `json:"status"`
}

type batchManagerStatusRequest struct {
	ManagerIDs []uint `json:"manager_ids" binding:"required,min=1,max=200"`
	Status     string `json:"status" binding:"required,oneof=active expired disabled"`
}

type batchRenewalKeyRevokeRequest struct {
	KeyIDs []uint `json:"key_ids" binding:"required,min=1,max=500"`
}

type batchRenewalKeyDeleteRequest struct {
	IDs []uint `json:"ids" binding:"required,min=1,max=500"`
}

type batchActivationCodeDeleteRequest struct {
	CodeIDs []uint `json:"code_ids" binding:"required,min=1,max=500"`
}

// ── New request types ───────────────────────────────

type patchGameProfileRequest struct {
	LoginID       *string `json:"login_id"`
	Progress      *string `json:"progress"`
	AccountStatus *string `json:"account_status"`
	CurrentTask   *string `json:"current_task"`
	Remark        *string `json:"remark"`
}

type putRestConfigRequest struct {
	Enabled      bool   `json:"enabled"`
	Mode         string `json:"mode" binding:"required,oneof=random custom"`
	RestStart    string `json:"rest_start"`
	RestDuration int    `json:"rest_duration"`
}

type createCoopAccountRequest struct {
	LoginID    string  `json:"login_id" binding:"required"`
	ExpireDate *string `json:"expire_date"`
	Note       string  `json:"note"`
}

type patchCoopAccountRequest struct {
	Status     *string `json:"status"`
	ExpireDate *string `json:"expire_date"`
	Note       *string `json:"note"`
}

type agentReportLogsRequest struct {
	Logs []agentLogEntry `json:"logs" binding:"required"`
}

type agentLogEntry struct {
	LogType string    `json:"type"`
	Level   string    `json:"level"`
	Message string    `json:"message"`
	Ts      time.Time `json:"ts"`
}
