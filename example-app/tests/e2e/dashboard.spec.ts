// @tags: smoke, p0, regression
// @jira: ACME-102
// @generated: playspec-v1

import { test, expect } from '@playwright/test';
import * as path from 'path';

const dashboardUrl = `file://${path.resolve(__dirname, '../../dashboard.html')}`;

test.describe('Dashboard', () => {
  test('displays navigation links', async ({ page }) => {
    await page.goto(dashboardUrl);
    await expect(page.getByTestId('nav-orders')).toBeVisible();
    await expect(page.getByTestId('nav-products')).toBeVisible();
    await expect(page.getByTestId('nav-reports')).toBeVisible();
  });

  test('shows stat cards', async ({ page }) => {
    await page.goto(dashboardUrl);
    await expect(page.getByTestId('stat-orders')).toHaveText('142');
    await expect(page.getByTestId('stat-revenue')).toHaveText('$8,430');
    await expect(page.getByTestId('stat-customers')).toHaveText('89');
  });

  test('logout button navigates to login', async ({ page }) => {
    await page.goto(dashboardUrl);
    await page.getByTestId('logout').click();
    await expect(page).toHaveURL(/index/);
  });
});
