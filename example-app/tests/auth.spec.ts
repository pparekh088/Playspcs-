// @tags: smoke, auth
// @jira: PLAY-1
// @owner: team-qa
/**
 * Authentication Tests
 *
 * PLAY-1: User Login — Verify users can log in with valid credentials
 * PLAY-7: User Logout — Verify users can log out and return to the login screen
 */
import { test, expect } from '@playwright/test';

test.describe('PLAY-1: User Login', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display the login form', async ({ page }) => {
    await expect(page.locator('#login-page')).toBeVisible();
    await expect(page.locator('#email')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.getByTestId('login-button')).toBeVisible();
  });

  test('should log in with valid credentials', async ({ page }) => {
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();

    await expect(page.locator('#todo-page')).toBeVisible();
    await expect(page.locator('#login-page')).toBeHidden();
    await expect(page.locator('#user-email')).toHaveText('demo@test.com');
  });

  test('should show error for invalid email', async ({ page }) => {
    await page.locator('#email').fill('wrong@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();

    await expect(page.locator('#login-error')).toBeVisible();
    await expect(page.locator('#login-error')).toHaveText('Invalid email or password. Please try again.');
    await expect(page.locator('#login-page')).toBeVisible();
  });

  test('should show error for invalid password', async ({ page }) => {
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('wrongpassword');
    await page.getByTestId('login-button').click();

    await expect(page.locator('#login-error')).toBeVisible();
    await expect(page.locator('#login-page')).toBeVisible();
  });

  test('should show error when both credentials are wrong', async ({ page }) => {
    await page.locator('#email').fill('nobody@example.com');
    await page.locator('#password').fill('nope');
    await page.getByTestId('login-button').click();

    await expect(page.locator('#login-error')).toBeVisible();
  });

  test('should clear error on successful login after failed attempt', async ({ page }) => {
    // First: fail
    await page.locator('#email').fill('wrong@test.com');
    await page.locator('#password').fill('wrong');
    await page.getByTestId('login-button').click();
    await expect(page.locator('#login-error')).toBeVisible();

    // Then: succeed
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();

    await expect(page.locator('#todo-page')).toBeVisible();
  });
});

test.describe('PLAY-7: User Logout', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();
    await expect(page.locator('#todo-page')).toBeVisible();
  });

  test('should show logout button when logged in', async ({ page }) => {
    await expect(page.getByTestId('logout-button')).toBeVisible();
  });

  test('should return to login page on logout', async ({ page }) => {
    await page.getByTestId('logout-button').click();

    await expect(page.locator('#login-page')).toBeVisible();
    await expect(page.locator('#todo-page')).toBeHidden();
  });

  test('should clear todos on logout', async ({ page }) => {
    // Add a todo first
    await page.getByTestId('new-todo-input').fill('Task before logout');
    await page.getByTestId('add-todo-button').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(1);

    // Logout
    await page.getByTestId('logout-button').click();
    await expect(page.locator('#login-page')).toBeVisible();

    // Login again
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();

    // Todos should be gone
    await expect(page.getByTestId('todo-item')).toHaveCount(0);
  });

  test('should reset filters on logout', async ({ page }) => {
    // Switch to "Completed" filter
    await page.getByTestId('filter-completed').click();
    await expect(page.getByTestId('filter-completed')).toHaveClass(/active/);

    // Logout and login again
    await page.getByTestId('logout-button').click();
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();

    // "All" filter should be active again
    await expect(page.getByTestId('filter-all')).toHaveClass(/active/);
  });
});
