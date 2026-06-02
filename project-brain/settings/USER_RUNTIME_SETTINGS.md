# User Settings Panel

## Status: ✅ FULLY OPERATIONAL (Backend + Frontend)

## Architecture

### Backend (6 endpoints)
File: `backend/app/routers/settings.py`
Auth: `get_current_user` dependency — any authenticated user

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/settings/profile` | GET | Get user profile with tenant name |
| `/settings/profile` | PATCH | Update first_name, last_name, email |
| `/settings/change-password` | POST | Change password (verifies current) |
| `/settings/sessions` | GET | List tenant's WhatsApp sessions |
| `/settings/activity-log` | GET | Last 50 messages for tenant |
| `/settings/account` | DELETE | Soft-delete user account |

### Frontend UI
- Tab: "Settings" (visible to ALL authenticated users)
- Sections:
  - **Profile Information**: First name, last name, email fields with role/tenant/member-since display
  - **Security & Password**: Current password verification + new password change with confirmation
  - **Connected Sessions**: Audit view of all WhatsApp sessions linked to the tenant
  - **Activity Log**: Scrollable list of recent messages with direction badges and timestamps

### API Client Methods
Located in `frontend/src/lib/api.ts`, section 9:
```typescript
api.settings.getProfile()
api.settings.updateProfile({ first_name, last_name, email })
api.settings.changePassword({ current_password, new_password })
api.settings.getSessions()
api.settings.getActivityLog()
api.settings.deleteAccount()
```

### Data Flow
1. Tab activation triggers `fetchSettingsData()` via `useEffect`
2. Three parallel `Promise.allSettled` calls: profile, sessions, activity-log
3. Profile form fields are pre-populated from the API response
4. Update/password forms submit independently with success/error message feedback
5. Password change requires current password verification server-side
