package com.srp.client.renderer;

import com.srp.client.model.ProjectileHommingModel;
import com.srp.entity.ProjectileHommingEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ProjectileHommingRenderer extends GeoEntityRenderer<ProjectileHommingEntity> {

    public ProjectileHommingRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ProjectileHommingModel());
    }
}
