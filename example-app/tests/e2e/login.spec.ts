// @tags: smoke, p0, regression, auth
// @jira: ACME-101
// @generated: playspec-v1

import { test, expect } from '@playwright/test';
import * as path from 'path';

const loginUrl = `file://${path.resolve(__dirname, '../../index.html')}`;
const dashboardUrl = `file://${path.resolve(__dirname, '../../dashboard.html')}`;

test.describe('Login', () => {
  test.describe('Happy Path', () => {
    test('logs in with valid credentials', async ({ page }) => {
      await page.goto(loginUrl);
      await page.getByTestId('email').fill('user@example.com');
      await page.getByTestId('password').fill('password123');
      await page.getByTestId('submit-button').click();
      await expect(page).toHaveURL(/dashboard/);
    });

    test('shows dashboard after login', async ({ page }) => {
      await page.goto(dashboardUrl);
      await expect(page.getByTestId('dashboard-heading')).toHaveText('Dashboard');
      await expect(page.getByTestId('welcome-message')).toContainText('user@example.com');
    });
  });

  test.describe('Error States', () => {
    test('shows error for invalid credentials', async ({ page }) => {
      await page.goto(loginUrl);
      await page.getByTestId('email').fill('wrong@example.com');
      await page.getByTestId('password').fill('badpassword');
      await page.getByTestId('submit-button').click();
      await expect(page.getByTestId('error-message')).toBeVisible();
      await expect(page.getByTestId('error-message')).toContainText('Invalid');
    });

    test('stays on login page when credentials are wrong', async ({ page }) => {
      await page.goto(loginUrl);
      await page.getByTestId('email').fill('nobody@example.com');
      await page.getByTestId('password').fill('wrong');
      await page.getByTestId('submit-button').click();
      await expect(page).toHaveURL(/index/);
    });
  });
});
