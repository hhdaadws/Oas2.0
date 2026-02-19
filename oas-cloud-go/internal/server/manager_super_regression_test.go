package server

import (
	"net/http"
	"testing"
	"time"

	"oas-cloud-go/internal/models"
)

func TestExpiredManagerCanLoginAndRedeemRenewalKey(t *testing.T) {
	srv, db := setupTestServer(t)

	manager := createActiveManager(t, db, "manager_expired_case", "passwordExpired123")
	expiredAt := time.Now().UTC().Add(-2 * time.Hour)
	if err := db.Model(&models.Manager{}).Where("id = ?", manager.ID).Updates(map[string]any{
		"status":     models.ManagerStatusExpired,
		"expires_at": expiredAt,
		"updated_at": time.Now().UTC(),
	}).Error; err != nil {
		t.Fatalf("mark manager expired failed: %v", err)
	}

	loginResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/auth/login",
		map[string]any{
			"username": manager.Username,
			"password": "passwordExpired123",
		},
		"",
	)
	if loginResp.Code != http.StatusOK {
		t.Fatalf("expired manager login should pass, status=%d body=%s", loginResp.Code, loginResp.Body.String())
	}
	loginPayload := decodeBodyMap(t, loginResp.Body.Bytes())
	token, _ := loginPayload["token"].(string)
	if token == "" {
		t.Fatalf("manager token should not be empty")
	}
	expiredFlag, ok := loginPayload["expired"].(bool)
	if !ok || !expiredFlag {
		t.Fatalf("expired flag should be true")
	}

	overviewBeforeResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/manager/overview",
		nil,
		token,
	)
	if overviewBeforeResp.Code != http.StatusForbidden {
		t.Fatalf("expired manager should not access overview, status=%d body=%s", overviewBeforeResp.Code, overviewBeforeResp.Body.String())
	}

	renewalKey := models.ManagerRenewalKey{
		Code:                  "mrk_redeem_case_001",
		DurationDays:          30,
		Status:                models.CodeStatusUnused,
		CreatedBySuperAdminID: 1,
		CreatedAt:             time.Now().UTC(),
	}
	if err := db.Create(&renewalKey).Error; err != nil {
		t.Fatalf("create renewal key failed: %v", err)
	}

	redeemResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/auth/redeem-renewal-key",
		map[string]any{
			"code": renewalKey.Code,
		},
		token,
	)
	if redeemResp.Code != http.StatusOK {
		t.Fatalf("redeem renewal key should pass, status=%d body=%s", redeemResp.Code, redeemResp.Body.String())
	}

	overviewAfterResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/manager/overview",
		nil,
		token,
	)
	if overviewAfterResp.Code != http.StatusOK {
		t.Fatalf("manager should access overview after redeem, status=%d body=%s", overviewAfterResp.Code, overviewAfterResp.Body.String())
	}
}

func TestSuperListManagersUsesSnakeCaseFields(t *testing.T) {
	srv, db := setupTestServer(t)

	createSuperAdmin(t, db, "super_regression", "superPass123")
	createActiveManager(t, db, "manager_list_case", "managerPass123")

	superLoginResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/super/auth/login",
		map[string]any{
			"username": "super_regression",
			"password": "superPass123",
		},
		"",
	)
	if superLoginResp.Code != http.StatusOK {
		t.Fatalf("super login failed, status=%d body=%s", superLoginResp.Code, superLoginResp.Body.String())
	}
	superToken := extractTokenFromBody(t, superLoginResp.Body.Bytes())
	if superToken == "" {
		t.Fatalf("super token should not be empty")
	}

	listResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/super/managers",
		nil,
		superToken,
	)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list managers failed, status=%d body=%s", listResp.Code, listResp.Body.String())
	}
	payload := decodeBodyMap(t, listResp.Body.Bytes())
	items, ok := payload["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatalf("items should be non-empty array")
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("first manager should be object")
	}
	if _, ok := first["id"]; !ok {
		t.Fatalf("manager payload should contain snake_case id field")
	}
	if _, ok := first["username"]; !ok {
		t.Fatalf("manager payload should contain snake_case username field")
	}
	if _, ok := first["status"]; !ok {
		t.Fatalf("manager payload should contain snake_case status field")
	}
	if _, ok := first["expires_at"]; !ok {
		t.Fatalf("manager payload should contain snake_case expires_at field")
	}
	if _, hasUpper := first["ID"]; hasUpper {
		t.Fatalf("manager payload should not expose upper-case ID field")
	}
}

func TestSuperListManagerRenewalKeysShowsStatusAndUsage(t *testing.T) {
	srv, db := setupTestServer(t)

	createSuperAdmin(t, db, "super_key_list", "superPass123")
	manager := createActiveManager(t, db, "manager_key_used", "managerPass123")
	usedAt := time.Now().UTC()
	keys := []models.ManagerRenewalKey{
		{
			Code:                  "mrk_key_unused",
			DurationDays:          30,
			Status:                models.CodeStatusUnused,
			CreatedBySuperAdminID: 1,
			CreatedAt:             time.Now().UTC(),
		},
		{
			Code:                  "mrk_key_used",
			DurationDays:          60,
			Status:                models.CodeStatusUsed,
			UsedByManagerID:       &manager.ID,
			UsedAt:                &usedAt,
			CreatedBySuperAdminID: 1,
			CreatedAt:             time.Now().UTC(),
		},
	}
	if err := db.Create(&keys).Error; err != nil {
		t.Fatalf("create renewal keys failed: %v", err)
	}

	superLoginResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/super/auth/login",
		map[string]any{
			"username": "super_key_list",
			"password": "superPass123",
		},
		"",
	)
	if superLoginResp.Code != http.StatusOK {
		t.Fatalf("super login failed, status=%d body=%s", superLoginResp.Code, superLoginResp.Body.String())
	}
	superToken := extractTokenFromBody(t, superLoginResp.Body.Bytes())

	listResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/super/manager-renewal-keys?limit=50",
		nil,
		superToken,
	)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list renewal keys failed, status=%d body=%s", listResp.Code, listResp.Body.String())
	}

	payload := decodeBodyMap(t, listResp.Body.Bytes())
	items, ok := payload["items"].([]any)
	if !ok || len(items) < 2 {
		t.Fatalf("renewal key items should contain at least 2 entries")
	}

	var foundUsed bool
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if item["code"] == "mrk_key_used" {
			foundUsed = true
			if item["status"] != models.CodeStatusUsed {
				t.Fatalf("expected used key status=used, got %v", item["status"])
			}
			if item["used_by_manager_username"] != manager.Username {
				t.Fatalf("expected used_by_manager_username=%s, got %v", manager.Username, item["used_by_manager_username"])
			}
		}
	}
	if !foundUsed {
		t.Fatalf("should find used renewal key in list response")
	}
}
