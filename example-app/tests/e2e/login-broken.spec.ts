// @tags: smoke, p0, regression, auth
// @jira: ACME-103
// @generated: playspec-v1
// NOTE: This file contains intentional failures to exercise the repair pipeline.

import { test, expect } from '@playwright/test';
import * as path from 'path';

const loginUrl = `file://${path.resolve(__dirname, '../../index.html')}`;

test.describe('Login — broken selectors (repair target)', () => {
  test('logs in with valid credentials', async ({ page }) => {
    await page.goto(loginUrl);
    // BROKEN: old selector IDs no longer exist — these were renamed to data-testid
    await page.locator('#email-input').fill('user@example.com');
    await page.locator('#password-input').fill('password123');
    await page.locator('#login-btn').click();
    await expect(page).toHaveURL(/dashboard/);
  });

  test('shows error for wrong password', async ({ page }) => {
    await page.goto(loginUrl);
    await page.locator('#email-input').fill('user@example.com');
    await page.locator('#password-input').fill('wrong');
    await page.locator('#login-btn').click();
    // BROKEN: wrong assertion — error text was updated
    await expect(page.locator('#error-msg')).toHaveText('Incorrect password.');
  });
});
