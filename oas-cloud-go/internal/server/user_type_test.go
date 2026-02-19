package server

import (
	"net/http"
	"testing"
)

func TestRegisterByTypedCodeBindsUserTypeAndTaskPool(t *testing.T) {
	srv, db := setupTestServer(t)
	manager := createActiveManager(t, db, "manager_type_bind", "passwordTypeBind123")
	managerToken := loginManagerToken(t, srv, manager.Username, "passwordTypeBind123")

	createCodeResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/activation-codes",
		map[string]any{
			"duration_days": 30,
			"user_type":     "duiyi",
		},
		managerToken,
	)
	if createCodeResp.Code != http.StatusCreated {
		t.Fatalf("create activation code failed, status=%d body=%s", createCodeResp.Code, createCodeResp.Body.String())
	}
	createPayload := decodeBodyMap(t, createCodeResp.Body.Bytes())
	code, _ := createPayload["code"].(string)
	if code == "" {
		t.Fatalf("activation code should not be empty")
	}

	registerResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/user/auth/register-by-code",
		map[string]any{"code": code},
		"",
	)
	if registerResp.Code != http.StatusCreated {
		t.Fatalf("register by code failed, status=%d body=%s", registerResp.Code, registerResp.Body.String())
	}
	registerPayload := decodeBodyMap(t, registerResp.Body.Bytes())
	if registerPayload["user_type"] != "duiyi" {
		t.Fatalf("expected user_type=duiyi, got %v", registerPayload["user_type"])
	}
	userToken, _ := registerPayload["token"].(string)
	if userToken == "" {
		t.Fatalf("user token should not be empty")
	}

	taskResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/user/me/tasks",
		nil,
		userToken,
	)
	if taskResp.Code != http.StatusOK {
		t.Fatalf("get me tasks failed, status=%d body=%s", taskResp.Code, taskResp.Body.String())
	}
	taskPayload := decodeBodyMap(t, taskResp.Body.Bytes())
	if taskPayload["user_type"] != "duiyi" {
		t.Fatalf("expected task user_type=duiyi, got %v", taskPayload["user_type"])
	}
	taskConfig, ok := taskPayload["task_config"].(map[string]any)
	if !ok {
		t.Fatalf("task_config should be object")
	}
	if len(taskConfig) != 1 {
		t.Fatalf("duiyi task pool should have exactly one task, got %d", len(taskConfig))
	}
	if _, exists := taskConfig["对弈竞猜"]; !exists {
		t.Fatalf("duiyi task pool should contain 对弈竞猜")
	}
	if _, exists := taskConfig["寄养"]; exists {
		t.Fatalf("duiyi task pool should not contain 寄养")
	}
}

func TestDuiyiUserCannotUpdateNonDuiyiTask(t *testing.T) {
	srv, db := setupTestServer(t)
	manager := createActiveManager(t, db, "manager_type_guard", "passwordTypeGuard123")
	managerToken := loginManagerToken(t, srv, manager.Username, "passwordTypeGuard123")

	createCodeResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/activation-codes",
		map[string]any{
			"duration_days": 30,
			"user_type":     "duiyi",
		},
		managerToken,
	)
	if createCodeResp.Code != http.StatusCreated {
		t.Fatalf("create activation code failed, status=%d body=%s", createCodeResp.Code, createCodeResp.Body.String())
	}
	code := decodeBodyMap(t, createCodeResp.Body.Bytes())["code"].(string)

	registerResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/user/auth/register-by-code",
		map[string]any{"code": code},
		"",
	)
	if registerResp.Code != http.StatusCreated {
		t.Fatalf("register by code failed, status=%d body=%s", registerResp.Code, registerResp.Body.String())
	}
	userToken := decodeBodyMap(t, registerResp.Body.Bytes())["token"].(string)

	updateResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPut,
		"/api/v1/user/me/tasks",
		map[string]any{
			"task_config": map[string]any{
				"寄养": map[string]any{
					"enabled": true,
				},
			},
		},
		userToken,
	)
	if updateResp.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for disallowed task update, got %d body=%s", updateResp.Code, updateResp.Body.String())
	}
}

func TestRedeemTypedCodeSwitchesUserTypeAndTaskPool(t *testing.T) {
	srv, db := setupTestServer(t)
	manager := createActiveManager(t, db, "manager_type_switch", "passwordTypeSwitch123")
	managerToken := loginManagerToken(t, srv, manager.Username, "passwordTypeSwitch123")

	createDailyResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/activation-codes",
		map[string]any{
			"duration_days": 30,
			"user_type":     "daily",
		},
		managerToken,
	)
	if createDailyResp.Code != http.StatusCreated {
		t.Fatalf("create daily activation code failed, status=%d body=%s", createDailyResp.Code, createDailyResp.Body.String())
	}
	dailyCode := decodeBodyMap(t, createDailyResp.Body.Bytes())["code"].(string)

	registerResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/user/auth/register-by-code",
		map[string]any{"code": dailyCode},
		"",
	)
	if registerResp.Code != http.StatusCreated {
		t.Fatalf("register by daily code failed, status=%d body=%s", registerResp.Code, registerResp.Body.String())
	}
	userToken := decodeBodyMap(t, registerResp.Body.Bytes())["token"].(string)

	createShuakaResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/activation-codes",
		map[string]any{
			"duration_days": 30,
			"user_type":     "shuaka",
		},
		managerToken,
	)
	if createShuakaResp.Code != http.StatusCreated {
		t.Fatalf("create shuaka activation code failed, status=%d body=%s", createShuakaResp.Code, createShuakaResp.Body.String())
	}
	shuakaCode := decodeBodyMap(t, createShuakaResp.Body.Bytes())["code"].(string)

	redeemResp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/user/auth/redeem-code",
		map[string]any{"code": shuakaCode},
		userToken,
	)
	if redeemResp.Code != http.StatusOK {
		t.Fatalf("redeem shuaka code failed, status=%d body=%s", redeemResp.Code, redeemResp.Body.String())
	}
	redeemPayload := decodeBodyMap(t, redeemResp.Body.Bytes())
	if redeemPayload["user_type"] != "shuaka" {
		t.Fatalf("expected user_type=shuaka after redeem, got %v", redeemPayload["user_type"])
	}

	taskResp := doJSONRequest(
		t,
		srv.router,
		http.MethodGet,
		"/api/v1/user/me/tasks",
		nil,
		userToken,
	)
	if taskResp.Code != http.StatusOK {
		t.Fatalf("get me tasks failed, status=%d body=%s", taskResp.Code, taskResp.Body.String())
	}
	taskConfig := decodeBodyMap(t, taskResp.Body.Bytes())["task_config"].(map[string]any)
	if _, exists := taskConfig["起号_租借式神"]; !exists {
		t.Fatalf("shuaka task pool should contain 起号_租借式神")
	}
	if _, exists := taskConfig["寄养"]; exists {
		t.Fatalf("shuaka task pool should not contain 寄养")
	}
}

func loginManagerToken(t *testing.T, srv *Server, username string, password string) string {
	t.Helper()
	resp := doJSONRequest(
		t,
		srv.router,
		http.MethodPost,
		"/api/v1/manager/auth/login",
		map[string]any{
			"username": username,
			"password": password,
		},
		"",
	)
	if resp.Code != http.StatusOK {
		t.Fatalf("manager login failed, status=%d body=%s", resp.Code, resp.Body.String())
	}
	token := extractTokenFromBody(t, resp.Body.Bytes())
	if token == "" {
		t.Fatalf("manager token should not be empty")
	}
	return token
}
