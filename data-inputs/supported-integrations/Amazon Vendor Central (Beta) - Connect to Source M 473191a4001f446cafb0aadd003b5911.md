# Amazon Vendor Central (Beta) - Connect to Source Medium

Tags: Integration, Premium
Platform Category: eCommerce / Retail

---

[Getting started with Source Medium](https://www.notion.so/Getting-started-with-Source-Medium-c5767189520342c0a404f2d0045dd44d?pvs=21)

[Integration Docs](https://www.notion.so/Integration-Docs-2c27a8bf6ec74d7d8c63d6d66fa82a7d?pvs=21)

[FAQ](https://www.notion.so/FAQ-2ce974d908834aa7a3e73800657dbf03?pvs=21)

**©** [Source Medium 2023](https://www.sourcemedium.com/)

## Follow this integration guide to connect your Amazon Vendor Central data to Source Medium.

### Requirements

- **Admin or Global Admin access** to your Amazon Vendor Central account
- Be able to add Source Medium as a new user and adjust permissions
- Premium Integration

### FAQ

- Do we really need to grant Source Medium all these permissions?
    - Yes, the permissions are necessary for us to programmatically access all of the most important data. If we ever become aware of decreased permissions for certain roles, we will let you know ASAP. Rest assured, we take our data security very seriously at Source Medium and your data will never be used for any purposes outside of reporting without your explicit consent.

### **Steps**

Add Source Medium as a user in Vendor Central

- Click `Admin or Global Admin Permissions` under `Settings > Manage Permissions`

![Untitled](Amazon%20Vendor%20Central%20(Beta)%20-%20Connect%20to%20Source%20M%20473191a4001f446cafb0aadd003b5911/Untitled.png)

- Under **Add a New User**, enter the email address of the user you want to invite to the account ([integrations@sourcemedium.com](mailto:integrations@sourcemedium.com))
    
    ![Untitled](Amazon%20Vendor%20Central%20(Beta)%20-%20Connect%20to%20Source%20M%20473191a4001f446cafb0aadd003b5911/Untitled%201.png)
    
- Click **Invite**. The email invitation is sent to the email address you specified.
- Once Source Medium accepts the invitation, apply these permissions (flip the circled No to Yes):
    
    ![Untitled](Amazon%20Vendor%20Central%20(Beta)%20-%20Connect%20to%20Source%20M%20473191a4001f446cafb0aadd003b5911/Untitled%202.png)
    
- Double-check that `Yes` permission is selected for the following items:
    - **Financial reports** View reports relating to sales, payments, and overall vendor performance
    - **Operational reports** View reports relating to catalog data quality, missing images, and other non-sales related metrics
    - **Manage Integrations (EDI/API)** Create, update, and monitor EDI and API Integrations
    - **Digital Reports** View reports regarding your digital products, including sales and performance metrics
    - Click **Continue**
- Once we are added as a user with the correct permissions, we will be able to integrate your data into your dashboard!

---

> [FAQ article on the new Amazon SP-API integration](https://help.sourcemedium.com/articles/what-are-the-implications-of-the-new-beta-amazon-sp-api-integration)
>