package server

import (
	"net/http"
	"time"

	"gorm.io/gorm"
	"oas-cloud-go/internal/auth"
	"oas-cloud-go/internal/models"

	"github.com/gin-gonic/gin"
)

const (
	ctxActorRoleKey   = "actor_role"
	ctxActorIDKey     = "actor_id"
	ctxManagerIDKey   = "manager_id"
	ctxUserIDKey      = "user_id"
	ctxUserTokenIDKey = "user_token_id"
)

func (s *Server) requireJWT(roles ...string) gin.HandlerFunc {
	allowed := map[string]struct{}{}
	for _, role := range roles {
		allowed[role] = struct{}{}
	}

	return func(c *gin.Context) {
		raw := auth.BearerToken(c.GetHeader("Authorization"))
		if raw == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "missing bearer token"})
			c.Abort()
			return
		}

		claims, err := s.tokenManager.ParseJWT(raw)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "invalid token"})
			c.Abort()
			return
		}
		if _, ok := allowed[claims.Role]; !ok {
			c.JSON(http.StatusForbidden, gin.H{"detail": "forbidden"})
			c.Abort()
			return
		}
		if claims.Role == models.ActorTypeAgent {
			ok, err := s.redisStore.ValidateAgentSession(c.Request.Context(), raw, claims.ManagerID)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"detail": "redis session check failed"})
				c.Abort()
				return
			}
			if !ok {
				c.JSON(http.StatusUnauthorized, gin.H{"detail": "agent session expired"})
				c.Abort()
				return
			}
		}

		c.Set(ctxActorRoleKey, claims.Role)
		c.Set(ctxActorIDKey, claims.SubjectID)
		c.Set(ctxManagerIDKey, claims.ManagerID)
		c.Next()
	}
}

func (s *Server) requireUserToken() gin.HandlerFunc {
	return func(c *gin.Context) {
		raw := auth.BearerToken(c.GetHeader("Authorization"))
		if raw == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "missing bearer token"})
			c.Abort()
			return
		}

		hash := auth.HashToken(raw)
		now := time.Now().UTC()
		var token models.UserToken
		if err := s.db.Where("token_hash = ? AND revoked_at IS NULL AND expires_at > ?", hash, now).First(&token).Error; err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "invalid user token"})
			c.Abort()
			return
		}
		var user models.User
		if err := s.db.Where("id = ?", token.UserID).First(&user).Error; err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "user not found"})
			c.Abort()
			return
		}
		if user.Status != models.UserStatusActive {
			c.JSON(http.StatusForbidden, gin.H{"detail": "user not active"})
			c.Abort()
			return
		}
		if user.ExpiresAt == nil || !user.ExpiresAt.After(now) {
			c.JSON(http.StatusForbidden, gin.H{"detail": "user expired"})
			c.Abort()
			return
		}

		token.LastUsedAt = &now
		_ = s.db.Model(&models.UserToken{}).Where("id = ?", token.ID).Update("last_used_at", now).Error

		c.Set(ctxActorRoleKey, models.ActorTypeUser)
		c.Set(ctxActorIDKey, user.ID)
		c.Set(ctxUserIDKey, user.ID)
		c.Set(ctxUserTokenIDKey, token.ID)
		c.Set(ctxManagerIDKey, user.ManagerID)
		c.Next()
	}
}

func (s *Server) requireManagerActive() gin.HandlerFunc {
	return func(c *gin.Context) {
		managerID := getUint(c, ctxActorIDKey)
		if managerID == 0 {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "missing manager identity"})
			c.Abort()
			return
		}

		var manager models.Manager
		if err := s.db.Where("id = ?", managerID).First(&manager).Error; err != nil {
			if err == gorm.ErrRecordNotFound {
				c.JSON(http.StatusUnauthorized, gin.H{"detail": "manager not found"})
				c.Abort()
				return
			}
			c.JSON(http.StatusInternalServerError, gin.H{"detail": "failed to query manager"})
			c.Abort()
			return
		}

		now := time.Now().UTC()
		if manager.Status == models.ManagerStatusDisabled {
			c.JSON(http.StatusForbidden, gin.H{"detail": "manager disabled"})
			c.Abort()
			return
		}
		if manager.ExpiresAt == nil || !manager.ExpiresAt.After(now) || manager.Status != models.ManagerStatusActive {
			c.JSON(http.StatusForbidden, gin.H{"detail": "manager expired"})
			c.Abort()
			return
		}
		c.Next()
	}
}

func getUint(c *gin.Context, key string) uint {
	value, exists := c.Get(key)
	if !exists {
		return 0
	}
	casted, ok := value.(uint)
	if !ok {
		return 0
	}
	return casted
}
