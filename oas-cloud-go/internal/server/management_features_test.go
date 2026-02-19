package server

import (
	"net/http"
	"testing"
	"time"

	"oas-cloud-go/internal/models"
)

func TestManagerActivationCodeListAndRevoke(t *testing.T) {
	srv, db := setupTestServer(t)
	managerA := createActiveManager(t, db, "manager_codes_a", "passwordCodesA123")
	managerB := createActiveManager(t, db, "manager_codes_b", "passwordCodesB123")
	tokenA := loginManagerToken(t, srv, managerA.Username, "passwordCodesA123")
	tokenB := loginManagerToken(t, srv, managerB.Username, "passwordCodesB123")

	createResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/activation-codes",
		map[string]any{
			"duration_days": 30,
			"user_type":     "daily",
		},
		tokenA,
	)
	if createResp.Code != http.StatusCreated {
		t.Fatalf("create activation code failed, status=%d body=%s", createResp.Code, createResp.Body.String())
	}
	code := decodeBodyMap(t, createResp.Body.Bytes())["code"].(string)

	listResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/manager/activation-codes?limit=50",
		nil,
		tokenA,
	)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list activation codes failed, status=%d body=%s", listResp.Code, listResp.Body.String())
	}
	payload := decodeBodyMap(t, listResp.Body.Bytes())
	items, ok := payload["items"].([]any)
	if !ok || len(items) == 0 {
		t.Fatalf("activation code items should be non-empty")
	}

	var codeID uint
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if item["code"] == code {
			codeID = uint(item["id"].(float64))
			break
		}
	}
	if codeID == 0 {
		t.Fatalf("created activation code should be listed")
	}

	revokeResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPatch,
		"/api/v1/manager/activation-codes/"+itoa(codeID)+"/status",
		map[string]any{
			"status": "revoked",
		},
		tokenA,
	)
	if revokeResp.Code != http.StatusOK {
		t.Fatalf("revoke activation code failed, status=%d body=%s", revokeResp.Code, revokeResp.Body.String())
	}

	var codeRecord models.UserActivationCode
	if err := db.Where("id = ?", codeID).First(&codeRecord).Error; err != nil {
		t.Fatalf("query activation code failed: %v", err)
	}
	if codeRecord.Status != models.CodeStatusRevoked {
		t.Fatalf("expected revoked status, got %s", codeRecord.Status)
	}

	createOtherResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/activation-codes",
		map[string]any{
			"duration_days": 15,
			"user_type":     "duiyi",
		},
		tokenB,
	)
	if createOtherResp.Code != http.StatusCreated {
		t.Fatalf("manager B create activation code failed, status=%d body=%s", createOtherResp.Code, createOtherResp.Body.String())
	}
	otherCode := decodeBodyMap(t, createOtherResp.Body.Bytes())["code"].(string)
	var otherRecord models.UserActivationCode
	if err := db.Where("code = ?", otherCode).First(&otherRecord).Error; err != nil {
		t.Fatalf("query manager B activation code failed: %v", err)
	}

	crossRevokeResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPatch,
		"/api/v1/manager/activation-codes/"+itoa(otherRecord.ID)+"/status",
		map[string]any{
			"status": "revoked",
		},
		tokenA,
	)
	if crossRevokeResp.Code != http.StatusNotFound {
		t.Fatalf("cross-manager revoke should be 404, status=%d body=%s", crossRevokeResp.Code, crossRevokeResp.Body.String())
	}
}

func TestSuperPatchManagerLifecycleAndRevokeRenewalKey(t *testing.T) {
	srv, db := setupTestServer(t)
	createSuperAdmin(t, db, "super_mgmt_case", "superMgmtPass123")
	manager := createActiveManager(t, db, "manager_lifecycle_case", "managerPass123")

	expiredAt := time.Now().UTC().Add(-4 * time.Hour)
	if err := db.Model(&models.Manager{}).Where("id = ?", manager.ID).Updates(map[string]any{
		"status":     models.ManagerStatusExpired,
		"expires_at": expiredAt,
		"updated_at": time.Now().UTC(),
	}).Error; err != nil {
		t.Fatalf("mark manager expired failed: %v", err)
	}

	superLoginResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/super/auth/login",
		map[string]any{
			"username": "super_mgmt_case",
			"password": "superMgmtPass123",
		},
		"",
	)
	if superLoginResp.Code != http.StatusOK {
		t.Fatalf("super login failed, status=%d body=%s", superLoginResp.Code, superLoginResp.Body.String())
	}
	superToken := extractTokenFromBody(t, superLoginResp.Body.Bytes())

	extendResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPatch,
		"/api/v1/super/managers/"+itoa(manager.ID)+"/lifecycle",
		map[string]any{
			"extend_days": 30,
		},
		superToken,
	)
	if extendResp.Code != http.StatusOK {
		t.Fatalf("super extend manager failed, status=%d body=%s", extendResp.Code, extendResp.Body.String())
	}

	var refreshed models.Manager
	if err := db.Where("id = ?", manager.ID).First(&refreshed).Error; err != nil {
		t.Fatalf("query manager failed: %v", err)
	}
	if refreshed.Status != models.ManagerStatusActive {
		t.Fatalf("manager should be active after extend, got %s", refreshed.Status)
	}
	if refreshed.ExpiresAt == nil || !refreshed.ExpiresAt.After(time.Now().UTC()) {
		t.Fatalf("manager expiry should be in the future after extend")
	}

	key := models.ManagerRenewalKey{
		Code:                  "mrk_super_revoke_case",
		DurationDays:          30,
		Status:                models.CodeStatusUnused,
		CreatedBySuperAdminID: 1,
		CreatedAt:             time.Now().UTC(),
	}
	if err := db.Create(&key).Error; err != nil {
		t.Fatalf("create manager renewal key failed: %v", err)
	}

	revokeResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPatch,
		"/api/v1/super/manager-renewal-keys/"+itoa(key.ID)+"/status",
		map[string]any{
			"status": "revoked",
		},
		superToken,
	)
	if revokeResp.Code != http.StatusOK {
		t.Fatalf("revoke manager renewal key failed, status=%d body=%s", revokeResp.Code, revokeResp.Body.String())
	}

	var refreshedKey models.ManagerRenewalKey
	if err := db.Where("id = ?", key.ID).First(&refreshedKey).Error; err != nil {
		t.Fatalf("query renewal key failed: %v", err)
	}
	if refreshedKey.Status != models.CodeStatusRevoked {
		t.Fatalf("renewal key should be revoked, got %s", refreshedKey.Status)
	}
}
